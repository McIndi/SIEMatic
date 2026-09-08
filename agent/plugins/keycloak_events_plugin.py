"""Checkpointed collector for Keycloak user events."""

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import logging

import requests

from agent.plugins.base import (
    CheckpointedPlugin,
    PermanentDeliveryError,
    build_batch,
    collection_status,
    fetch_checkpoints,
)


logger = logging.getLogger(__name__)


def _canonical_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True)


def event_fingerprint(event):
    event_id = event.get('id') if isinstance(event, dict) else None
    if isinstance(event_id, str) and event_id:
        return event_id
    return hashlib.sha256(_canonical_json(event).encode('utf-8')).hexdigest()


def encode_cursor(cursor):
    return _canonical_json(cursor)


def decode_cursor(cursor):
    if not cursor:
        return None
    value = json.loads(cursor)
    if (
        not isinstance(value, dict)
        or set(value) != {'timestamp', 'fingerprints'}
        or not isinstance(value['timestamp'], int)
        or not isinstance(value['fingerprints'], list)
    ):
        raise ValueError('invalid keycloak_events cursor')
    return value


class KeycloakApiClient:
    """Keycloak Admin REST client with one refresh-and-retry on HTTP 401."""

    def __init__(self, config, session=None):
        self.base_url = config['base_url'].rstrip('/')
        self.client_id = config.get('client_id', 'admin-cli')
        self.client_secret = config.get('client_secret')
        self.username = config.get('username')
        self.password = config.get('password')
        self.token_realm = config.get('token_realm', 'master')
        self.timeout = float(config.get('timeout', 20))
        self.verify = config.get('ca_bundle') or True
        self.session = session or requests.Session()
        self._token = None

    def _authenticate(self):
        data = {'client_id': self.client_id}
        if self.client_secret:
            data.update({
                'grant_type': 'client_credentials',
                'client_secret': self.client_secret,
            })
        elif self.username and self.password:
            data.update({
                'grant_type': 'password',
                'username': self.username,
                'password': self.password,
            })
        else:
            raise ValueError('Keycloak client credentials are not configured')
        response = self.session.post(
            f'{self.base_url}/realms/{self.token_realm}/protocol/openid-connect/token',
            data=data,
            timeout=self.timeout,
            verify=self.verify,
        )
        response.raise_for_status()
        self._token = response.json()['access_token']
        self.session.headers.update({'Authorization': f'Bearer {self._token}'})

    def _get(self, path, params=None):
        if self._token is None:
            self._authenticate()
        response = self.session.get(
            f'{self.base_url}{path}',
            params=params,
            timeout=self.timeout,
            verify=self.verify,
        )
        if response.status_code == 401:
            self._token = None
            self._authenticate()
            response = self.session.get(
                f'{self.base_url}{path}',
                params=params,
                timeout=self.timeout,
                verify=self.verify,
            )
        response.raise_for_status()
        return response

    def assert_events_enabled(self, realm):
        representation = self._get(f'/admin/realms/{realm}').json()
        if not representation.get('eventsEnabled'):
            raise RuntimeError(f'Keycloak user events are disabled for realm {realm}')

    def fetch_events(
        self, realm, *, date_from, date_to, first, max_results
    ):
        return self._get(
            f'/admin/realms/{realm}/events',
            {
                'dateFrom': str(date_from),
                'dateTo': str(date_to),
                'first': first,
                'max': max_results,
            },
        ).json()


class KeycloakEventsPlugin(CheckpointedPlugin):
    """Poll one Keycloak realm without advancing beyond acknowledged events."""

    def __init__(self, config, event_queue, ack_queue, stop_event, client=None):
        super().__init__(config, event_queue, ack_queue, stop_event)
        self.realm = config['realm']
        self.index = config.get('index', 'keycloak')
        self.source = config.get('source', f'keycloak/{self.realm}')
        self.host = config.get('host', 'keycloak')
        self.target_id = f'keycloak_events:{self.realm}'
        self.poll_interval = float(config.get('poll_interval', 30))
        self.page_size = min(int(config.get('page_size', 100)), 1000)
        self.max_pages = int(config.get('max_pages', 100))
        self.batch_size = min(int(config.get('batch_size', 200)), 500)
        self.max_batch_bytes = int(config.get('max_batch_bytes', 900_000))
        self.max_cursor_length = int(config.get('max_cursor_length', 16_384))
        if min(self.page_size, self.max_pages, self.batch_size) < 1:
            raise ValueError('Keycloak collection bounds must be positive')
        self.client = client or KeycloakApiClient(config['keycloak'])

    def _fetch_pages(self, date_from, date_to):
        events = []
        for page in range(self.max_pages):
            first = page * self.page_size
            result = self.client.fetch_events(
                self.realm,
                date_from=date_from,
                date_to=date_to,
                first=first,
                max_results=self.page_size,
            )
            if not isinstance(result, list):
                raise ValueError('Keycloak events response is not a list')
            events.extend(result)
            if len(result) < self.page_size:
                return events
        raise RuntimeError('Keycloak event pagination exceeded max_pages')

    @staticmethod
    def _cursor(events):
        timestamp = max(event['time'] for event in events)
        return encode_cursor({
            'timestamp': timestamp,
            'fingerprints': [
                event_fingerprint(event)
                for event in events
                if event['time'] == timestamp
            ],
        })

    def _build_batches(self, events):
        batches = []
        chunk = []
        chunk_bytes = 0

        def finish_chunk():
            nonlocal chunk, chunk_bytes
            if not chunk:
                return
            cursor = self._cursor(chunk)
            if len(cursor) > self.max_cursor_length:
                raise ValueError('one Keycloak timestamp exceeds max_cursor_length')
            routed = [
                {
                    'index': self.index,
                    'source': self.source,
                    'host': self.host,
                    'sourcetype': 'json',
                    'data': event,
                }
                for event in chunk
            ]
            batches.append(build_batch(
                agent=self.agent,
                target=self.target_id,
                cursor=cursor,
                events=routed,
                record_identities=[event_fingerprint(event) for event in chunk],
            ))
            chunk = []
            chunk_bytes = 0

        for event in events:
            event_size = len(_canonical_json(event).encode('utf-8'))
            if event_size > self.max_batch_bytes:
                raise ValueError('one Keycloak event exceeds max_batch_bytes')
            same_timestamp = bool(chunk and chunk[-1]['time'] == event['time'])
            exceeds = chunk and (
                len(chunk) >= self.batch_size
                or chunk_bytes + event_size > self.max_batch_bytes
            )
            if exceeds and not same_timestamp:
                finish_chunk()
            elif same_timestamp and (
                len(chunk) >= 500
                or chunk_bytes + event_size > self.max_batch_bytes
            ):
                raise ValueError('one Keycloak timestamp exceeds protocol bounds')
            chunk.append(event)
            chunk_bytes += event_size
        finish_chunk()
        return batches

    def collect_once(self, timestamp=None):
        if self.target_id in self.failed_targets:
            return []
        started = timestamp or datetime.now(timezone.utc)
        started_ms = int(started.timestamp() * 1000)
        cursor_string = self.read_positions.get(
            self.target_id, self.acknowledged_positions.get(self.target_id)
        )
        cursor = decode_cursor(cursor_string)
        if cursor is None:
            cursor = {'timestamp': started_ms, 'fingerprints': []}
            self.read_positions[self.target_id] = encode_cursor(cursor)
        try:
            raw_events = self._fetch_pages(
                cursor['timestamp'], max(started_ms, cursor['timestamp'])
            )
            boundary = Counter(cursor['fingerprints'])
            unique = set()
            events = []
            for event in raw_events:
                if not isinstance(event, dict) or not isinstance(event.get('time'), int):
                    raise ValueError('Keycloak event has no integer time')
                fingerprint = event_fingerprint(event)
                identity = (event['time'], fingerprint)
                if identity in unique:
                    continue
                unique.add(identity)
                if event['time'] < cursor['timestamp']:
                    continue
                if event['time'] == cursor['timestamp'] and boundary[fingerprint]:
                    boundary[fingerprint] -= 1
                    continue
                events.append(event)
            events.sort(key=lambda event: (event['time'], event_fingerprint(event)))
            batches = self._build_batches(events)
        except Exception as exc:
            logger.exception('Failed to collect Keycloak events for %s', self.realm)
            self.enqueue_batch(collection_status(
                'error',
                source='keycloak_events',
                host=self.agent.get('hostname') or 'localhost',
                error=str(exc),
                collection_target=self.target_id,
            ))
            return []
        if batches:
            self.read_positions[self.target_id] = batches[-1]['cursor']
        return batches

    def run(self):
        self.client.assert_events_enabled(self.realm)
        checkpoints = fetch_checkpoints(
            self.config['indexer'],
            self.config.get('indexer_credentials'),
            [self.target_id],
            self.agent,
        )
        self.acknowledged_positions.update(checkpoints)
        self.read_positions.update(checkpoints)
        while not self.stop_event.is_set():
            for batch in self.collect_once():
                try:
                    self.deliver_batch(batch)
                except PermanentDeliveryError:
                    logger.exception('Permanently stopped Keycloak event target')
            self.stop_event.wait(self.poll_interval)
