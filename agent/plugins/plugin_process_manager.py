"""
Plugin process manager for agent plugins.
Handles plugin lifecycle, authentication, and process management.
"""

import logging
logger = logging.getLogger(__name__)
logger.debug("agent.plugins.plugin_process_manager module loaded.")
import time
import multiprocessing
import importlib
import ssl
import websockets
import asyncio
import json
import requests
from pathlib import Path


def get_indexer_transport(indexer_cfg):
    """Return HTTP/WS schemes plus verification settings for the indexer."""
    tls_enabled = bool(indexer_cfg.get('tls', False))
    ca_bundle = indexer_cfg.get('ca_bundle')

    if ca_bundle:
        ca_path = Path(ca_bundle)
        if not ca_path.is_file():
            raise ValueError(f'INDEXER_CA_BUNDLE does not exist: {ca_path}')

    websocket_ssl = None
    if tls_enabled:
        websocket_ssl = ssl.create_default_context(cafile=ca_bundle)

    return {
        'http_scheme': 'https' if tls_enabled else 'http',
        'websocket_scheme': 'wss' if tls_enabled else 'ws',
        # requests verifies against system roots when this is True.
        'requests_verify': ca_bundle or True,
        'websocket_ssl': websocket_ssl,
    }


def run_plugin(plugin_path, config, event_queue, ack_queue, stop_event):
    """
    Run a plugin given its path and config, managing its lifecycle.
    """
    logger.info("run_plugin called with path=%s, config=%s", plugin_path, config)
    try:
        module_path, class_name = plugin_path.split(':')
        logger.debug("Importing module %s, class %s", module_path, class_name)
        module = importlib.import_module(module_path)
        plugin_cls = getattr(module, class_name)
        from agent.plugins.base import CheckpointedPlugin

        if issubclass(plugin_cls, CheckpointedPlugin):
            plugin = plugin_cls(config, event_queue, ack_queue, stop_event)
        else:
            plugin = plugin_cls(config, event_queue, stop_event)
        logger.info("Instantiated plugin %s with config %s", plugin_cls, config)
        if hasattr(plugin, 'run'):
            logger.info("Running plugin %s", plugin_cls)
            plugin.run()
        else:
            logger.warning("Plugin %s has no 'run' method, entering keep-alive loop.", plugin_cls)
            while not stop_event.is_set():
                time.sleep(1)
    except Exception as e:
        logger.exception("Exception in run_plugin: %s", e)


def get_session_cookie(indexer_cfg, credentials):
    """
    Authenticate with indexer and return session cookie.
    """
    import re
    logger.info(f"get_session_cookie called with indexer_cfg={indexer_cfg}, credentials={'***' if credentials else None}")
    host = indexer_cfg.get('host', 'localhost')
    port = indexer_cfg.get('port', 8000)
    transport = get_indexer_transport(indexer_cfg)
    logger.info(
        "Authenticating to indexer at %s://%s:%s",
        transport['http_scheme'],
        host,
        port,
    )
    login_url = f"{transport['http_scheme']}://{host}:{port}/login/"
    if not credentials:
        raise ValueError("Credentials are required for authentication")
    with requests.Session() as session:
        resp = session.get(login_url, verify=transport['requests_verify'])
        text = resp.text
        csrf_token = session.cookies.get('csrftoken')
        if not csrf_token:
            match = re.search(r'name=["\']csrfmiddlewaretoken["\'] value=["\']([^"\']+)["\']', text)
            if match:
                csrf_token = match.group(1)
        if not csrf_token:
            return None
        payload = {
            'username': credentials['username'],
            'password': credentials['password'],
            'csrfmiddlewaretoken': csrf_token
        }
        login_headers = {
            'Referer': login_url
        }
        resp = session.post(
            login_url,
            data=payload,
            headers=login_headers,
            allow_redirects=False,
            verify=transport['requests_verify'],
        )
        if resp.status_code not in (200, 302):
            logger.error("Login failed with status code %d", resp.status_code)
            return None
        sessionid = session.cookies.get('sessionid')
        if not sessionid:
            return None
        return sessionid

async def authenticate(indexer_cfg, credentials, max_retries=5):
    """
    Log in to the indexer and return a session cookie.

    Called before every connection attempt rather than once at startup. A
    Django session expires, and the indexer rejects the WebSocket handshake
    when it does. Reusing the cookie obtained at startup means every later
    reconnect presents the same dead credential, so the sender retries
    forever without ever sending another event.

    Args:
        indexer_cfg: The indexer configuration.
        credentials: Mapping with username and password.
        max_retries: Attempts before giving up.

    Returns:
        str or None: The session cookie, or None if every attempt failed.
    """
    for attempt in range(max_retries):
        try:
            sessionid = get_session_cookie(indexer_cfg, credentials)
        except requests.RequestException:
            # A refused connection or a DNS failure during login is the
            # normal case while the indexer is still starting, and is worth
            # another attempt rather than ending the process.
            logger.exception("Could not reach the indexer to authenticate")
            sessionid = None
        if sessionid:
            return sessionid
        wait_time = 2 ** attempt  # exponential backoff
        logger.warning(
            "Login failed, retrying in %s seconds (attempt %d/%d)",
            wait_time, attempt + 1, max_retries,
        )
        await asyncio.sleep(wait_time)
    return None


def _is_complete_batch(item):
    return isinstance(item, dict) and all(
        field in item
        for field in ('_target', '_agent', 'agent_id', 'batch_id', 'cursor', 'events')
    )


def _batch_envelope(batch):
    return {
        'type': 'batch',
        'agent_id': batch['agent_id'],
        'target': batch['_target'],
        'batch_id': batch['batch_id'],
        'cursor': batch['cursor'],
        'events': batch['events'],
    }


def sender_process(event_queue, indexer_cfg, credentials=None, ack_queue=None):
    """
    Send events to the indexer via WebSocket.
    """
    logger.info(f"sender_process started with indexer_cfg={indexer_cfg}")
    async def send_events():
        host = indexer_cfg.get('host', 'localhost')
        port = indexer_cfg.get('port', 8000)
        transport = get_indexer_transport(indexer_cfg)
        uri = f"{transport['websocket_scheme']}://{host}:{port}/indexer/"

        # Held across reconnects on purpose. A batch drained from the queue is
        # gone from it, so if the send fails the only remaining copy is here.
        # Clearing it inside the connection loop loses every event in flight
        # whenever the indexer restarts. Bounded by the drain limit below,
        # because nothing is drained while a batch is still owed.
        pending = None

        while True:
            sessionid = await authenticate(indexer_cfg, credentials)
            if not sessionid:
                logger.error("Failed to authenticate after retries, sender_process exiting")
                return
            connect_options = {
                'additional_headers': {'Cookie': f"sessionid={sessionid}"},
            }
            if transport['websocket_ssl'] is not None:
                connect_options['ssl'] = transport['websocket_ssl']
            logger.info(f"Connecting to WebSocket {uri}")
            try:
                async with websockets.connect(uri, **connect_options) as websocket:
                    logger.info(f"WebSocket connection established to {uri}")
                    resumed_agent_id = None
                    while True:
                        if pending is None:
                            try:
                                first = event_queue.get_nowait()
                            except Exception:
                                first = None
                            if _is_complete_batch(first):
                                pending = first
                            elif first is not None:
                                pending = [first]
                                deadline = time.time() + 0.5
                                while len(pending) < 500 and time.time() < deadline:
                                    try:
                                        pending.append(event_queue.get_nowait())
                                    except Exception:
                                        break
                                for event in pending:
                                    if 'type' not in event:
                                        event['type'] = 'event'
                        if pending is None:
                            await asyncio.sleep(0.1)
                            continue
                        if _is_complete_batch(pending):
                            if ack_queue is None:
                                raise ValueError('A checkpointed batch requires an ack queue')
                            agent = pending['_agent']
                            if resumed_agent_id != agent['agent_id']:
                                await websocket.send(json.dumps({
                                    'type': 'resume',
                                    'agent': agent,
                                    'targets': [pending['_target']],
                                }))
                                resume = json.loads(await asyncio.wait_for(
                                    websocket.recv(),
                                    timeout=indexer_cfg.get('ack_timeout', 30),
                                ))
                                if resume.get('type') == 'nack':
                                    resume['status'] = resume.pop('type')
                                    resume['target'] = pending['_target']
                                    resume['batch_id'] = pending['batch_id']
                                    ack_queue.put(resume)
                                    pending = None
                                    continue
                                if resume.get('type') != 'resume_result':
                                    raise ConnectionError(
                                        f'Unexpected resume response: {resume!r}'
                                    )
                                resumed_agent_id = agent['agent_id']

                            await websocket.send(json.dumps(_batch_envelope(pending)))
                            response = json.loads(await asyncio.wait_for(
                                websocket.recv(),
                                timeout=indexer_cfg.get('ack_timeout', 30),
                            ))
                            if (
                                response.get('type') not in {'ack', 'nack'}
                                or response.get('target') != pending['_target']
                                or response.get('batch_id') != pending['batch_id']
                            ):
                                raise ConnectionError(
                                    f'Unexpected batch response: {response!r}'
                                )
                            response['status'] = response.pop('type')
                            ack_queue.put(response)
                            pending = None
                        else:
                            await websocket.send(json.dumps(pending))
                            pending = None
            except Exception as e:
                logger.exception(f"Exception in sender_process WebSocket loop: {e}")
                if _is_complete_batch(pending):
                    if ack_queue is not None:
                        ack_queue.put({
                            'target': pending['_target'],
                            'batch_id': pending['batch_id'],
                            'status': 'retry',
                        })
                    pending = None
                elif pending:
                    logger.warning(
                        "Holding %d event(s) for the next connection", len(pending)
                    )
                await asyncio.sleep(2)
    try:
        asyncio.run(send_events())
    except Exception as e:
        logger.exception(f"Exception in sender_process: {e}")


class PluginProcessManager:
    """
    Manage the lifecycle of plugin processes, including starting, stopping,
    and monitoring their status. Also manages the sender process for
    communicating with the indexer.
    """
    def __init__(self, plugin_path, config, indexer_cfg, credentials=None):
        self.plugin_path = plugin_path
        self.config = config
        self.indexer_cfg = indexer_cfg
        self.credentials = credentials
        self.restart_limit = config.get('restart', 3)
        self.child_processes = []
        self.restart_attempts = {}  # key by plugin_path
        queue_size = int(config.get('queue_size', 100))
        self.event_queue = multiprocessing.Queue(maxsize=queue_size)
        self.ack_queue = multiprocessing.Queue(maxsize=queue_size)
        self.sender_proc = None
        self.stop_event = multiprocessing.Event()  # add stop_event
        logger.debug(f"PluginProcessManager initialized for {plugin_path} with config {config}")

    def start(self):
        """
        Start the plugin process and the sender process.
        """
        logger.info(f"Starting plugin process for {self.plugin_path}")
        proc = multiprocessing.Process(
            target=run_plugin,
            args=(
                self.plugin_path,
                self.config,
                self.event_queue,
                self.ack_queue,
                self.stop_event,
            ),
        )
        proc.start()
        logger.info(f"Started plugin process with PID {proc.pid}")
        self.child_processes.append(proc)
        self.restart_attempts[self.plugin_path] = 0  # initialize attempts by plugin_path
        # Start sender process
        if not self.sender_proc or not self.sender_proc.is_alive():
            logger.info("Starting sender process")
            self.sender_proc = multiprocessing.Process(
                target=sender_process,
                args=(
                    self.event_queue,
                    self.indexer_cfg,
                    self.credentials,
                    self.ack_queue,
                ),
            )
            self.sender_proc.start()
            logger.info(f"Started sender process with PID {self.sender_proc.pid}")

    def check_and_restart(self):
        """
        Check the status of child processes and restart them if they are not alive.
        """
        for proc in list(self.child_processes):
            if not proc.is_alive():
                attempts = self.restart_attempts.get(self.plugin_path, 0)  # get attempts by plugin_path
                logger.warning(f"Plugin process PID {proc.pid} is not alive. Restart attempts: {attempts}")
                if attempts < self.restart_limit:
                    new_proc = multiprocessing.Process(
                        target=run_plugin,
                        args=(
                            self.plugin_path,
                            self.config,
                            self.event_queue,
                            self.ack_queue,
                            self.stop_event,
                        ),
                    )
                    new_proc.start()
                    logger.info(f"Restarted plugin process with new PID {new_proc.pid}")
                    self.child_processes.append(new_proc)
                    self.restart_attempts[self.plugin_path] = attempts + 1  # increment by plugin_path
                else:
                    logger.error(f"Restart limit reached for plugin process PID {proc.pid}")
                self.child_processes.remove(proc)
        # Restart sender if needed
        if self.sender_proc and not self.sender_proc.is_alive():
            logger.warning(f"Sender process PID {self.sender_proc.pid} is not alive. Attempting restart.")
            self.sender_proc = multiprocessing.Process(
                target=sender_process,
                args=(
                    self.event_queue,
                    self.indexer_cfg,
                    self.credentials,
                    self.ack_queue,
                ),
            )
            self.sender_proc.start()
            logger.info(f"Restarted sender process with PID {self.sender_proc.pid}")

    def children_alive(self):
        """
        Check if child processes are alive.
        """
        alive = sum([p.is_alive() for p in self.child_processes])
        if self.sender_proc and self.sender_proc.is_alive():
            alive += 1
        logger.debug(f"children_alive: {alive} (plugin processes: {len(self.child_processes)}, sender alive: {self.sender_proc.is_alive() if self.sender_proc else False})")
        return alive

    def stop(self):
        """
        Stop the plugin processes gracefully.
        """
        logger.info(f"Stopping plugin processes for {self.plugin_path}")
        self.stop_event.set()
        for proc in self.child_processes:
            if proc.is_alive():
                proc.join(timeout=5)
                if proc.is_alive():
                    logger.warning(f"Plugin process {proc.pid} did not stop gracefully, terminating")
                    proc.terminate()
        if self.sender_proc and self.sender_proc.is_alive():
            self.sender_proc.terminate()  # sender might need to be terminated as it has its own loop
        logger.info(f"Stopped all processes for {self.plugin_path}")
