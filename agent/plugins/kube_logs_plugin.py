"""Checkpointed collector for Kubernetes container logs."""

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
from urllib.parse import quote

import requests

from agent.plugins.base import (
    CheckpointedPlugin,
    PermanentDeliveryError,
    build_batch,
    collection_status,
    fetch_checkpoints,
)


logger = logging.getLogger(__name__)


def encode_cursor(cursor):
    return json.dumps(cursor, ensure_ascii=False, separators=(',', ':'), sort_keys=True)


def decode_cursor(cursor):
    if not cursor:
        return None
    value = json.loads(cursor)
    required = {
        'timestamp',
        'line_hashes',
        'pod_uid',
        'container_id',
        'restart_count',
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError('invalid kube_logs cursor')
    if not isinstance(value['line_hashes'], list):
        raise ValueError('invalid kube_logs cursor line hashes')
    return value


def _rfc3339(value):
    value = value.astimezone(timezone.utc)
    if value.microsecond:
        return value.isoformat(timespec='microseconds').replace('+00:00', 'Z')
    return value.isoformat(timespec='seconds').replace('+00:00', 'Z')


class KubernetesApiClient:
    """Small Kubernetes REST client limited to pods and pod logs."""

    token_path = Path('/var/run/secrets/kubernetes.io/serviceaccount/token')
    ca_path = Path('/var/run/secrets/kubernetes.io/serviceaccount/ca.crt')

    def __init__(self, config=None, session=None):
        config = config or {}
        host = os.getenv('KUBERNETES_SERVICE_HOST')
        port = os.getenv('KUBERNETES_SERVICE_PORT_HTTPS', '443')
        self.api_url = config.get('api_url') or (
            f'https://{host}:{port}' if host else None
        )
        if not self.api_url:
            raise ValueError('Kubernetes API URL is not configured')

        token = config.get('token')
        if token is None and self.token_path.exists():
            token = self.token_path.read_text(encoding='utf-8').strip()
        if not token:
            raise ValueError('Kubernetes API token is not configured')

        ca_bundle = config.get('ca_bundle')
        if ca_bundle is None and self.ca_path.exists():
            ca_bundle = str(self.ca_path)
        self.verify = ca_bundle if ca_bundle is not None else True
        self.timeout = float(config.get('timeout', 15))
        self.session = session or requests.Session()
        self.session.headers.update({'Authorization': f'Bearer {token}'})

    def _get(self, path, params=None):
        response = self.session.get(
            f'{self.api_url.rstrip("/")}{path}',
            params=params,
            timeout=self.timeout,
            verify=self.verify,
        )
        response.raise_for_status()
        return response

    def resolve_pod(self, target):
        namespace = quote(target['namespace'], safe='')
        selector = target.get('selector')
        if target.get('deployment'):
            deployment = quote(target['deployment'], safe='')
            response = self._get(
                f'/apis/apps/v1/namespaces/{namespace}/deployments/{deployment}'
            )
            labels = response.json().get('spec', {}).get('selector', {}).get(
                'matchLabels', {}
            )
            if not labels:
                raise ValueError('deployment has no matchLabels selector')
            selector = ','.join(
                f'{key}={value}' for key, value in sorted(labels.items())
            )

        response = self._get(
            f'/api/v1/namespaces/{namespace}/pods',
            {'labelSelector': selector},
        )
        candidates = [
            pod for pod in response.json().get('items', [])
            if pod.get('status', {}).get('phase') == 'Running'
            and any(
                status.get('name') == target['container']
                for status in pod.get('status', {}).get('containerStatuses', [])
            )
        ]
        if not candidates:
            raise LookupError(
                f'no running pod for {target["namespace"]}/{selector}'
            )
        return max(
            candidates,
            key=lambda pod: (
                pod.get('metadata', {}).get('creationTimestamp', ''),
                pod.get('metadata', {}).get('name', ''),
            ),
        )

    def read_logs(self, pod_name, container, *, since_time=None, previous=False):
        namespace = quote(self._namespace, safe='')
        pod_name = quote(pod_name, safe='')
        params = {'container': container, 'timestamps': 'true'}
        if since_time is not None:
            params['sinceTime'] = since_time
        if previous:
            params['previous'] = 'true'
        return self._get(
            f'/api/v1/namespaces/{namespace}/pods/{pod_name}/log', params
        ).text

    def set_namespace(self, namespace):
        self._namespace = namespace


class KubeLogsPlugin(CheckpointedPlugin):
    """Poll configured pod logs and retain each batch until it is acknowledged."""

    def __init__(self, config, event_queue, ack_queue, stop_event, client=None):
        super().__init__(config, event_queue, ack_queue, stop_event)
        self.targets = config.get('targets', [])
        if not self.targets:
            raise ValueError('kube_logs requires at least one target')
        for target in self.targets:
            if bool(target.get('deployment')) == bool(target.get('selector')):
                raise ValueError('target requires exactly one of deployment or selector')
            for field in ('namespace', 'container', 'index', 'source', 'sourcetype'):
                if not target.get(field):
                    raise ValueError(f'target requires {field}')
        self.poll_interval = float(config.get('poll_interval', 5))
        # At most 200 boundary hashes also keeps the encoded cursor below the
        # indexer's 16 KiB cursor limit when every event shares a timestamp.
        self.batch_size = min(int(config.get('batch_size', 200)), 200)
        self.max_batch_bytes = int(config.get('max_batch_bytes', 900_000))
        self.max_cursor_length = int(config.get('max_cursor_length', 16_384))
        if self.batch_size < 1 or self.max_batch_bytes < 1:
            raise ValueError('batch bounds must be positive')
        self.client = client or KubernetesApiClient(config.get('kubernetes'))

    @staticmethod
    def line_hash(line):
        return hashlib.sha256(line.encode('utf-8')).hexdigest()

    @staticmethod
    def target_id(target):
        selector = target.get('deployment') or target['selector']
        return f'kube_logs:{target["namespace"]}/{selector}/{target["container"]}'

    @staticmethod
    def _container_identity(pod, container):
        statuses = pod.get('status', {}).get('containerStatuses', [])
        status = next(
            (item for item in statuses if item.get('name') == container),
            None,
        )
        if status is None:
            raise LookupError(f'container status not found for {container}')
        return {
            'pod_uid': pod['metadata']['uid'],
            'container_id': status.get('containerID') or '',
            'restart_count': int(status.get('restartCount', 0)),
        }

    @staticmethod
    def _parse_lines(raw):
        records = []
        for raw_line in raw.splitlines():
            timestamp, separator, line = raw_line.partition(' ')
            if not separator or not timestamp or not line:
                logger.warning('Ignoring container log line without timestamp prefix')
                continue
            records.append((timestamp, line))
        return records

    def _after_boundary(self, records, cursor):
        if cursor is None:
            return records
        boundary = cursor['timestamp']
        remaining = Counter(cursor['line_hashes'])
        selected = []
        for timestamp, line in records:
            if timestamp < boundary:
                continue
            digest = self.line_hash(line)
            if timestamp == boundary and remaining[digest]:
                remaining[digest] -= 1
                continue
            selected.append((timestamp, line))
        return selected

    def _event(self, target, pod_name, line):
        routing = {
            'index': target['index'],
            'source': target['source'],
            'host': pod_name,
            'sourcetype': target['sourcetype'],
        }
        if target.get('vault_audit'):
            prefix = target.get('prefix', '')
            if prefix:
                if not line.startswith(prefix):
                    return None
                line = line[len(prefix):]
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                return None
            if not isinstance(record, dict) or record.get('type') not in {
                'request', 'response'
            }:
                return None
            return {**routing, 'data': record}
        return {**routing, 'data': line}

    def _cursor(self, records, identity):
        latest = max(timestamp for timestamp, _line in records)
        hashes = [
            self.line_hash(line)
            for timestamp, line in records
            if timestamp == latest
        ]
        return encode_cursor({
            'timestamp': latest,
            'line_hashes': hashes,
            **identity,
        })

    def _collect_target(self, target, started):
        target_id = self.target_id(target)
        if target_id in self.failed_targets:
            return None
        cursor_string = self.read_positions.get(
            target_id, self.acknowledged_positions.get(target_id)
        )
        cursor = decode_cursor(cursor_string)
        pod = self.client.resolve_pod(target)
        pod_name = pod['metadata']['name']
        identity = self._container_identity(pod, target['container'])
        if hasattr(self.client, 'set_namespace'):
            self.client.set_namespace(target['namespace'])

        same_pod = cursor and cursor['pod_uid'] == identity['pod_uid']
        same_container = same_pod and all(
            cursor[field] == identity[field]
            for field in ('container_id', 'restart_count')
        )
        streams = []
        if same_container:
            raw = self.client.read_logs(
                pod_name,
                target['container'],
                since_time=cursor['timestamp'],
            )
            streams.append((self._parse_lines(raw), cursor, identity))
        elif same_pod:
            previous = self.client.read_logs(
                pod_name,
                target['container'],
                since_time=cursor['timestamp'],
                previous=True,
            )
            current = self.client.read_logs(
                pod_name, target['container'], since_time=None
            )
            old_identity = {
                field: cursor[field]
                for field in ('pod_uid', 'container_id', 'restart_count')
            }
            streams.extend([
                (self._after_boundary(self._parse_lines(previous), cursor), None, old_identity),
                (self._parse_lines(current), None, identity),
            ])
        else:
            since_time = None if cursor else _rfc3339(started)
            current = self.client.read_logs(
                pod_name, target['container'], since_time=since_time
            )
            streams.append((self._parse_lines(current), None, identity))

        records = []
        occurrences = defaultdict(int)
        for stream_records, boundary, stream_identity in streams:
            selected = self._after_boundary(stream_records, boundary)
            for timestamp, line in selected:
                records.append((timestamp, line, stream_identity))

        if not records:
            return []

        batches = []
        chunk_records = []
        chunk_events = []
        chunk_identities = []
        chunk_bytes = 0

        def finish_chunk():
            nonlocal chunk_records, chunk_events, chunk_identities, chunk_bytes
            if not chunk_events:
                return
            last_identity = chunk_records[-1][2]
            cursor_value = self._cursor(
                [(timestamp, line) for timestamp, line, _identity in chunk_records],
                last_identity,
            )
            if len(cursor_value) > self.max_cursor_length:
                raise ValueError('one timestamp boundary exceeds max_cursor_length')
            batches.append(build_batch(
                agent=self.agent,
                target=target_id,
                cursor=cursor_value,
                events=chunk_events,
                record_identities=chunk_identities,
            ))
            chunk_records = []
            chunk_events = []
            chunk_identities = []
            chunk_bytes = 0

        for timestamp, line, stream_identity in records:
            event = self._event(target, pod_name, line)
            event_size = 0
            if event is not None:
                event_size = len(json.dumps(event).encode('utf-8'))
                if event_size > self.max_batch_bytes:
                    raise ValueError('one Kubernetes log event exceeds max_batch_bytes')
                exceeds_preferred_bound = chunk_events and (
                    len(chunk_events) >= self.batch_size
                    or chunk_bytes + event_size > self.max_batch_bytes
                )
                same_timestamp = bool(
                    chunk_records and chunk_records[-1][0] == timestamp
                )
                if exceeds_preferred_bound and not same_timestamp:
                    finish_chunk()
                elif same_timestamp and (
                    len(chunk_events) >= 500
                    or chunk_bytes + event_size > self.max_batch_bytes
                ):
                    raise ValueError('one timestamp boundary exceeds protocol bounds')

            chunk_records.append((timestamp, line, stream_identity))
            if event is not None:
                digest = self.line_hash(line)
                identity_key = (
                    stream_identity['pod_uid'],
                    stream_identity['container_id'],
                    stream_identity['restart_count'],
                    timestamp,
                    digest,
                )
                occurrence = occurrences[identity_key]
                occurrences[identity_key] += 1
                chunk_events.append(event)
                chunk_identities.append([*identity_key, occurrence])
                chunk_bytes += event_size

        finish_chunk()
        if batches:
            self.read_positions[target_id] = batches[-1]['cursor']
        else:
            last_identity = records[-1][2]
            self.read_positions[target_id] = self._cursor(
                [(timestamp, line) for timestamp, line, _identity in records],
                last_identity,
            )
        return batches

    def collect_once(self, timestamp=None):
        started = timestamp or datetime.now(timezone.utc)
        batches = []
        for target in self.targets:
            try:
                target_batches = self._collect_target(target, started)
            except Exception as exc:
                logger.exception('Failed to collect Kubernetes logs for %s', target)
                self.enqueue_batch(collection_status(
                    'error',
                    source='kube_logs',
                    host=self.agent.get('hostname') or 'localhost',
                    error=str(exc),
                    collection_target=self.target_id(target),
                ))
                continue
            batches.extend(target_batches)
        return batches

    def run(self):
        target_ids = [self.target_id(target) for target in self.targets]
        checkpoints = fetch_checkpoints(
            self.config['indexer'],
            self.config.get('indexer_credentials'),
            target_ids,
            self.agent,
        )
        self.acknowledged_positions.update(checkpoints)
        self.read_positions.update(checkpoints)
        while not self.stop_event.is_set():
            for batch in self.collect_once():
                try:
                    self.deliver_batch(batch)
                except PermanentDeliveryError:
                    logger.exception('Permanently stopped Kubernetes log target')
            self.stop_event.wait(self.poll_interval)
