"""Shared primitives for checkpointed log shippers."""

import asyncio
import hashlib
import json
import queue
import time
from abc import ABC, abstractmethod
from threading import Lock


def _canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(',', ':'),
        sort_keys=True,
    )


def build_batch(*, agent, target, cursor, events, record_identities):
    """Build the immutable object retained by a plugin until acknowledgement."""
    identity = {
        'target': target,
        'cursor': cursor,
        'record_identities': list(record_identities),
    }
    batch_id = hashlib.sha256(_canonical_json(identity).encode('utf-8')).hexdigest()
    return {
        '_target': target,
        '_agent': dict(agent),
        'agent_id': agent['agent_id'],
        'batch_id': batch_id,
        'cursor': cursor,
        'events': list(events),
    }


def collection_status(state, *, source, error=None, host='localhost', **details):
    if state not in {'ok', 'partial', 'error'}:
        raise ValueError('state must be ok, partial, or error')
    event = {
        'event_type': 'collection_status',
        'collection_state': state,
        'collection_error': error,
        'index': 'agents',
        'source': source,
        'host': host,
        'sourcetype': 'json',
        'timestamp': time.time(),
    }
    event.update(details)
    return event


async def _fetch_checkpoints(indexer_cfg, credentials, targets, agent):
    from agent.plugins.plugin_process_manager import authenticate, get_indexer_transport
    import websockets

    transport = get_indexer_transport(indexer_cfg)
    sessionid = await authenticate(indexer_cfg, credentials)
    if not sessionid:
        raise ConnectionError('Unable to authenticate to the indexer')
    host = indexer_cfg.get('host', 'localhost')
    port = indexer_cfg.get('port', 8000)
    uri = f"{transport['websocket_scheme']}://{host}:{port}/indexer/"
    options = {
        'additional_headers': {'Cookie': f'sessionid={sessionid}'},
        'max_size': indexer_cfg.get('max_message_bytes', 1_048_576),
    }
    if transport['websocket_ssl'] is not None:
        options['ssl'] = transport['websocket_ssl']
    async with websockets.connect(uri, **options) as websocket:
        await websocket.send(_canonical_json({
            'type': 'resume',
            'agent': agent,
            'targets': list(targets),
        }))
        response = json.loads(await websocket.recv())
    if response.get('type') != 'resume_result' or not isinstance(
        response.get('checkpoints'), dict
    ):
        raise ConnectionError(f'Unexpected resume response: {response!r}')
    return response['checkpoints']


def fetch_checkpoints(indexer_cfg, credentials, targets, agent):
    """Fetch server-acknowledged cursors once when a checkpointed plugin starts."""
    return asyncio.run(_fetch_checkpoints(indexer_cfg, credentials, targets, agent))


class CheckpointedPlugin(ABC):
    """Base class that keeps a complete batch until the sender acknowledges it."""

    def __init__(self, config, event_queue, ack_queue, stop_event):
        self.config = config
        self.event_queue = event_queue
        self.ack_queue = ack_queue
        self.stop_event = stop_event
        self.agent = {
            'agent_id': config['agent_id'],
            'hostname': config.get('hostname', ''),
            'version': config.get('version', ''),
        }
        self.read_positions = {}
        self.acknowledged_positions = {}
        self._inflight = {}
        self._inflight_lock = Lock()
        self._ack_backlog = {}
        self._ack_lock = Lock()

    @abstractmethod
    def collect_once(self, timestamp=None):
        """Collect one bounded unit of source data."""

    def enqueue_batch(self, batch):
        """Apply bounded backpressure while allowing a graceful stop."""
        while not self.stop_event.is_set():
            try:
                self.event_queue.put(batch, timeout=0.5)
                return
            except queue.Full:
                continue
        raise RuntimeError('Plugin stopped before batch could be queued')

    def deliver_batch(self, batch, *, timeout=30):
        target = batch['_target']
        with self._inflight_lock:
            if target in self._inflight:
                raise RuntimeError(f'Batch already in flight for {target}')
            self._inflight[target] = batch
        try:
            while not self.stop_event.is_set():
                self.enqueue_batch(batch)
                deadline = time.monotonic() + timeout
                while not self.stop_event.is_set():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    acknowledgement = self._next_acknowledgement(
                        target,
                        batch['batch_id'],
                        remaining,
                    )
                    if acknowledgement is None:
                        break
                    if acknowledgement.get('status') == 'ack':
                        self.acknowledged_positions[target] = acknowledgement.get(
                            'cursor', batch['cursor']
                        )
                        return acknowledgement
                    break
            raise RuntimeError('Plugin stopped before batch was acknowledged')
        finally:
            with self._inflight_lock:
                self._inflight.pop(target, None)

    def _next_acknowledgement(self, target, batch_id, timeout):
        wanted = (target, batch_id)
        with self._ack_lock:
            backlog = self._ack_backlog.get(wanted)
            if backlog:
                acknowledgement = backlog.pop(0)
                if not backlog:
                    self._ack_backlog.pop(wanted, None)
                return acknowledgement

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            try:
                acknowledgement = self.ack_queue.get(timeout=remaining)
            except queue.Empty:
                return None
            received = (
                acknowledgement.get('target'),
                acknowledgement.get('batch_id'),
            )
            if received == wanted:
                return acknowledgement
            with self._ack_lock:
                self._ack_backlog.setdefault(received, []).append(acknowledgement)
