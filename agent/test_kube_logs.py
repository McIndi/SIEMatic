"""Contract tests for the checkpointed Kubernetes log collector."""

from datetime import datetime, timezone
from queue import Queue
from threading import Event

from django.test import SimpleTestCase

from agent.plugins.kube_logs_plugin import (
    KubeLogsPlugin,
    decode_cursor,
    encode_cursor,
)


class FakeKubernetesClient:
    def __init__(self, pod, *, current='', previous=''):
        self.pod = pod
        self.current = current
        self.previous = previous
        self.calls = []

    def resolve_pod(self, target):
        self.calls.append(('resolve', target['namespace']))
        return self.pod

    def read_logs(self, pod_name, container, *, since_time=None, previous=False):
        self.calls.append(('logs', pod_name, container, since_time, previous))
        return self.previous if previous else self.current


def pod(*, uid='pod-uid-1', container_id='containerd://one', restart_count=0):
    return {
        'metadata': {'name': 'weather-service-abc', 'uid': uid},
        'status': {
            'containerStatuses': [{
                'name': 'authbridge-proxy',
                'containerID': container_id,
                'restartCount': restart_count,
            }],
        },
    }


class KubeLogsPluginTests(SimpleTestCase):
    target = {
        'namespace': 'team1',
        'deployment': 'weather-service',
        'container': 'authbridge-proxy',
        'index': 'authbridge',
        'source': 'weather-service/authbridge-proxy',
        'sourcetype': 'logfmt',
    }

    def make_plugin(self, client, targets=None):
        return KubeLogsPlugin(
            {
                'agent_id': 'shipper-kube-logs',
                'hostname': 'collector-0',
                'version': '1.0',
                'targets': targets or [self.target],
                'poll_interval': 5,
            },
            Queue(maxsize=10),
            Queue(maxsize=10),
            Event(),
            client=client,
        )

    def test_cursor_round_trips_boundary_multiset_and_container_identity(self):
        cursor = {
            'timestamp': '2026-09-07T12:00:00.123456789Z',
            'line_hashes': ['hash-a', 'hash-a', 'hash-b'],
            'pod_uid': 'pod-uid-1',
            'container_id': 'containerd://one',
            'restart_count': 0,
        }

        self.assertEqual(decode_cursor(encode_cursor(cursor)), cursor)

    def test_inclusive_boundary_skips_consumed_occurrences_but_keeps_new_one(self):
        timestamp = '2026-09-07T12:00:00.123456789Z'
        line = 'level=info code=ibac.blocked'
        client = FakeKubernetesClient(
            pod(),
            current=(
                f'{timestamp} {line}\n'
                f'{timestamp} {line}\n'
                '2026-09-07T12:00:01.000000000Z level=info code=next\n'
            ),
        )
        plugin = self.make_plugin(client)
        target_id = plugin.target_id(self.target)
        first_hash = plugin.line_hash(line)
        plugin.acknowledged_positions[target_id] = encode_cursor({
            'timestamp': timestamp,
            'line_hashes': [first_hash],
            'pod_uid': 'pod-uid-1',
            'container_id': 'containerd://one',
            'restart_count': 0,
        })

        batches = plugin.collect_once()

        self.assertEqual(len(batches), 1)
        self.assertEqual([event['data'] for event in batches[0]['events']], [line, 'level=info code=next'])
        cursor = decode_cursor(batches[0]['cursor'])
        self.assertEqual(cursor['timestamp'], '2026-09-07T12:00:01.000000000Z')
        self.assertEqual(len(cursor['line_hashes']), 1)
        self.assertEqual(client.calls[-1][3], timestamp)

    def test_restart_collects_previous_and_current_container_before_advancing(self):
        old_timestamp = '2026-09-07T12:00:00.000000000Z'
        client = FakeKubernetesClient(
            pod(container_id='containerd://two', restart_count=1),
            previous='2026-09-07T12:00:01.000000000Z old-container-line\n',
            current='2026-09-07T12:00:02.000000000Z new-container-line\n',
        )
        plugin = self.make_plugin(client)
        target_id = plugin.target_id(self.target)
        plugin.acknowledged_positions[target_id] = encode_cursor({
            'timestamp': old_timestamp,
            'line_hashes': [],
            'pod_uid': 'pod-uid-1',
            'container_id': 'containerd://one',
            'restart_count': 0,
        })

        batches = plugin.collect_once()

        self.assertEqual(
            [event['data'] for event in batches[0]['events']],
            ['old-container-line', 'new-container-line'],
        )
        self.assertIn(
            ('logs', 'weather-service-abc', 'authbridge-proxy', old_timestamp, True),
            client.calls,
        )
        cursor = decode_cursor(batches[0]['cursor'])
        self.assertEqual(cursor['container_id'], 'containerd://two')
        self.assertEqual(cursor['restart_count'], 1)

    def test_vault_target_keeps_only_request_and_response_audit_records(self):
        vault_target = {
            'namespace': 'vault',
            'selector': 'app.kubernetes.io/name=vault',
            'container': 'vault',
            'index': 'vault',
            'source': 'vault/audit',
            'sourcetype': 'json',
            'vault_audit': True,
            'prefix': 'vault-audit: ',
        }
        client = FakeKubernetesClient(
            pod(),
            current=(
                '2026-09-07T12:00:01.000000000Z operational server message\n'
                '2026-09-07T12:00:02.000000000Z vault-audit: {"type":"request","request":{"path":"secret/"}}\n'
                '2026-09-07T12:00:03.000000000Z vault-audit: {"type":"response","response":{}}\n'
                '2026-09-07T12:00:04.000000000Z vault-audit: {"type":"other"}\n'
            ),
        )
        plugin = self.make_plugin(client, [vault_target])

        batches = plugin.collect_once(
            timestamp=datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
        )

        self.assertEqual(len(batches[0]['events']), 2)
        self.assertEqual(
            [event['type'] for event in batches[0]['events']],
            ['request', 'response'],
        )

    def test_unknown_target_starts_at_collection_time_not_retained_history(self):
        client = FakeKubernetesClient(
            pod(),
            current='2026-09-07T12:00:01.000000000Z new-line\n',
        )
        plugin = self.make_plugin(client)
        started = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)

        plugin.collect_once(timestamp=started)

        self.assertEqual(client.calls[-1][3], '2026-09-07T12:00:00Z')

    def test_invalid_target_requires_exactly_one_selector_kind(self):
        invalid = dict(self.target, selector='app=weather')

        with self.assertRaisesRegex(ValueError, 'deployment.*selector'):
            self.make_plugin(FakeKubernetesClient(pod()), [invalid])
