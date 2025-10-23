"""
Plugin process manager for agent plugins.
Handles plugin lifecycle, authentication, and process management.
"""

import base64
import logging
logger = logging.getLogger(__name__)
logger.debug("agent.plugins.plugin_process_manager module loaded.")
import time
import multiprocessing
import importlib
import websockets
import asyncio
import json
import requests
from django.urls import reverse


def run_plugin(plugin_path, config, event_queue, stop_event):
    """
    Run a plugin given its path and config, managing its lifecycle.
    """
    logger.info("run_plugin called with path=%s, config=%s", plugin_path, config)
    try:
        module_path, class_name = plugin_path.split(':')
        logger.debug("Importing module %s, class %s", module_path, class_name)
        module = importlib.import_module(module_path)
        plugin_cls = getattr(module, class_name)
        plugin = plugin_cls(config, event_queue, stop_event)  # pass stop_event
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
    logger.info(f"Authenticating to indexer at {host}:{port}")
    login_url = f"http://{host}:{port}/login/"
    if not credentials:
        raise ValueError("Credentials are required for authentication")
    with requests.Session() as session:
        resp = session.get(login_url)
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
        resp = session.post(login_url, data=payload, headers=login_headers, allow_redirects=False)
        if resp.status_code not in (200, 302):
            logger.error("Login failed with status code %d", resp.status_code)
            return None
        sessionid = session.cookies.get('sessionid')
        if not sessionid:
            return None
        return sessionid

def sender_process(event_queue, indexer_cfg, credentials=None):
    """
    Send events to the indexer via WebSocket.
    """
    logger.info(f"sender_process started with indexer_cfg={indexer_cfg}")
    async def send_events():
        host = indexer_cfg.get('host', 'localhost')
        port = indexer_cfg.get('port', 8000)
        headers = {}
        retry_count = 0
        max_retries = 5
        while retry_count < max_retries:
            sessionid = get_session_cookie(indexer_cfg, credentials)
            if sessionid:
                headers['Cookie'] = f"sessionid={sessionid}"
                break
            else:
                wait_time = 2 ** retry_count  # exponential backoff
                logger.warning(f"Login failed, retrying in {wait_time} seconds (attempt {retry_count + 1}/{max_retries})")
                await asyncio.sleep(wait_time)
                retry_count += 1
        if not sessionid:
            logger.error("Failed to authenticate after retries, sender_process exiting")
            return
        uri = f'ws://{host}:{port}/indexer/'
        logger.info(f"Connecting to WebSocket {uri} with headers {headers}")
        while True:
            try:
                async with websockets.connect(uri, additional_headers=headers) as websocket:
                    logger.info(f"WebSocket connection established to {uri}")
                    while True:
                        # Drain queue with soft limits
                        batch = []
                        deadline = time.time() + 0.5
                        while len(batch) < 500 and time.time() < deadline:
                            try:
                                batch.append(event_queue.get_nowait())
                            except Exception:
                                break
                        if not batch:
                            await asyncio.sleep(0.1)
                            continue
                        # Normalize type
                        for ev in batch:
                            if 'type' not in ev:
                                ev['type'] = 'event'
                        await websocket.send(json.dumps(batch))
            except Exception as e:
                logger.exception(f"Exception in sender_process WebSocket loop: {e}")
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
        self.event_queue = multiprocessing.Queue()
        self.sender_proc = None
        self.stop_event = multiprocessing.Event()  # add stop_event
        logger.debug(f"PluginProcessManager initialized for {plugin_path} with config {config}")

    def start(self):
        """
        Start the plugin process and the sender process.
        """
        logger.info(f"Starting plugin process for {self.plugin_path}")
        proc = multiprocessing.Process(target=run_plugin, args=(self.plugin_path, self.config, self.event_queue, self.stop_event))
        proc.start()
        logger.info(f"Started plugin process with PID {proc.pid}")
        self.child_processes.append(proc)
        self.restart_attempts[self.plugin_path] = 0  # initialize attempts by plugin_path
        # Start sender process
        if not self.sender_proc or not self.sender_proc.is_alive():
            logger.info("Starting sender process")
            self.sender_proc = multiprocessing.Process(target=sender_process, args=(self.event_queue, self.indexer_cfg, self.credentials))
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
                    new_proc = multiprocessing.Process(target=run_plugin, args=(self.plugin_path, self.config, self.event_queue, self.stop_event))
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
            self.sender_proc = multiprocessing.Process(target=sender_process, args=(self.event_queue, self.indexer_cfg, self.credentials))
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
