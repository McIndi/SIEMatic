"""Tests for agent transport configuration."""

import tempfile
import socket
import json
from datetime import timedelta
from io import StringIO
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
from threading import Event, Thread
from unittest.mock import Mock, patch

import psutil

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from agent.models import Agent, BatchReceipt, Checkpoint
from agent.plugins.base import (
    CheckpointedPlugin,
    PermanentDeliveryError,
    build_batch,
    collection_status,
    fetch_checkpoints,
)
from agent.plugins.plugin_process_manager import get_indexer_transport, sender_process
from agent.plugins.host_security_posture_plugin import HostSecurityPosturePlugin
from agent.plugins.network_security_plugin import NetworkSecurityPlugin
from agent.plugins.watchdog_plugin import WatchdogPlugin
from tools.gen_dev_cert import generate_certificate


class CheckpointModelTests(TestCase):
    def test_agent_and_checkpoint_identity_are_unique(self):
        user = get_user_model().objects.create_user(username='shipper')
        agent = Agent.objects.create(
            agent_id='cluster-a',
            user=user,
            hostname='node-a',
            address='192.0.2.10',
            version='1.0',
        )
        Checkpoint.objects.create(
            target='kube_logs:pod-a:container-a',
            cursor='cursor-1',
            agent=agent,
            index='kubernetes',
            source='pod-a/container-a',
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            Agent.objects.create(agent_id='cluster-a')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Checkpoint.objects.create(
                target='kube_logs:pod-a:container-a',
                cursor='cursor-2',
            )

    def test_batch_receipt_identity_is_scoped_to_target(self):
        BatchReceipt.objects.create(
            target='keycloak:realm-a',
            batch_id='batch-1',
            content_digest='a' * 64,
            cursor='cursor-1',
            count=2,
        )
        BatchReceipt.objects.create(
            target='keycloak:realm-b',
            batch_id='batch-1',
            content_digest='a' * 64,
            cursor='cursor-1',
            count=2,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            BatchReceipt.objects.create(
                target='keycloak:realm-a',
                batch_id='batch-1',
                content_digest='b' * 64,
                cursor='cursor-2',
                count=1,
            )

    def test_agent_group_has_only_shipper_permissions(self):
        group = Group.objects.get(name='Agent')

        self.assertEqual(
            set(group.permissions.values_list('content_type__app_label', 'codename')),
            {
                ('events', 'add_event'),
                ('agent', 'add_agent'),
                ('agent', 'change_agent'),
                ('agent', 'add_checkpoint'),
                ('agent', 'change_checkpoint'),
            },
        )


class ReceiptMaintenanceTests(TestCase):
    def test_prune_batch_receipts_removes_only_expired_rows(self):
        old = BatchReceipt.objects.create(
            target='old-target',
            batch_id='old-batch',
            content_digest='a' * 64,
            cursor='old',
            count=1,
        )
        current = BatchReceipt.objects.create(
            target='current-target',
            batch_id='current-batch',
            content_digest='b' * 64,
            cursor='current',
            count=1,
        )
        BatchReceipt.objects.filter(pk=old.pk).update(
            created=timezone.now() - timedelta(days=31)
        )

        output = StringIO()
        call_command('prune_batch_receipts', days=30, stdout=output)

        self.assertEqual(list(BatchReceipt.objects.values_list('pk', flat=True)), [current.pk])
        self.assertIn('Deleted 1', output.getvalue())


class ShipperSecurityCommandTests(TestCase):
    def test_check_shipper_users_fails_when_agent_can_also_read_events(self):
        user = get_user_model().objects.create_user(username='unsafe-shipper')
        user.groups.add(Group.objects.get(name='Agent'))
        user.groups.add(Group.objects.get(name='Registered User'))

        with self.assertRaisesRegex(CommandError, 'unsafe-shipper'):
            call_command('check_shipper_users')

    def test_check_shipper_users_accepts_write_only_agent(self):
        user = get_user_model().objects.create_user(username='safe-shipper')
        user.groups.add(Group.objects.get(name='Agent'))
        user.groups.remove(Group.objects.get(name='Registered User'))

        call_command('check_shipper_users', stdout=StringIO())

    def test_check_shipper_users_catches_direct_event_read_permission(self):
        user = get_user_model().objects.create_user(username='direct-reader')
        user.groups.add(Group.objects.get(name='Agent'))
        user.groups.remove(Group.objects.get(name='Registered User'))
        user.user_permissions.add(Permission.objects.get(
            content_type__app_label='events',
            codename='view_event',
        ))

        with self.assertRaisesRegex(CommandError, 'direct-reader'):
            call_command('check_shipper_users')


class HeartbeatPayloadTests(SimpleTestCase):
    def test_heartbeat_has_agent_identity_and_routing_metadata(self):
        from agent.management.commands.agent import build_heartbeat

        heartbeat = build_heartbeat(
            agent_id='shipper-a',
            hostname='node-a',
            children_alive={'plugin-a': True},
            plugin_managers={'plugin-a': {'alive': True, 'attempts': 0}},
            timestamp=123.0,
        )

        self.assertEqual(heartbeat['agent_id'], 'shipper-a')
        self.assertEqual(heartbeat['index'], 'agents')
        self.assertEqual(heartbeat['source'], 'agent_heartbeat')
        self.assertEqual(heartbeat['host'], 'node-a')
        self.assertEqual(heartbeat['sourcetype'], 'json')

    def test_checkpointed_plugin_receives_indexer_connection_details(self):
        from agent.management.commands.agent import build_plugin_config

        indexer = {'host': 'siematic-indexer', 'port': 8000}
        credentials = {'username': 'shipper', 'password': 'secret'}
        config = build_plugin_config(
            {'name': 'kube_logs', 'enabled': True},
            {
                'agent_id': 'kube-shipper',
                'hostname': 'collector-0',
                'indexer_credentials': credentials,
            },
            indexer,
        )

        self.assertEqual(config['indexer'], indexer)
        self.assertEqual(config['indexer_credentials'], credentials)


class IndexerTransportTests(SimpleTestCase):
    def test_plain_transport_remains_available(self):
        transport = get_indexer_transport({'tls': False})

        self.assertEqual(transport['http_scheme'], 'http')
        self.assertEqual(transport['websocket_scheme'], 'ws')
        self.assertIsNone(transport['websocket_ssl'])
        self.assertIs(transport['requests_verify'], True)

    def test_tls_transport_uses_ca_bundle_for_https_and_websocket(self):
        with tempfile.TemporaryDirectory() as directory:
            cert = Path(directory) / 'indexer.crt'
            key = Path(directory) / 'indexer.key'
            generate_certificate(cert, key, ['localhost'])

            transport = get_indexer_transport({
                'tls': True,
                'ca_bundle': str(cert),
            })

        self.assertEqual(transport['http_scheme'], 'https')
        self.assertEqual(transport['websocket_scheme'], 'wss')
        self.assertEqual(transport['requests_verify'], str(cert))
        self.assertIsNotNone(transport['websocket_ssl'])

    def test_missing_ca_bundle_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'INDEXER_CA_BUNDLE does not exist'):
            get_indexer_transport({
                'tls': True,
                'ca_bundle': 'missing-ca.pem',
            })


class _StopSender(BaseException):
    """
    Ends the sender loop from inside a test.

    A BaseException rather than an Exception because the sender catches
    Exception in two places and would otherwise reconnect forever.
    """


class _FakeWebSocket:
    def __init__(self, outcomes, sent):
        self._outcomes = outcomes
        self._sent = sent

    async def send(self, payload):
        self._sent.append(payload)
        outcome = self._outcomes.pop(0)
        if outcome is not None:
            raise outcome


def _fake_connect(outcomes, sent, cookies):
    """Stand in for websockets.connect, recording the cookie it was given."""
    class _Connection:
        def __init__(self, _uri, **options):
            cookies.append(options['additional_headers']['Cookie'])

        async def __aenter__(self):
            return _FakeWebSocket(outcomes, sent)

        async def __aexit__(self, *_exc):
            return False

    return _Connection


def _no_sleep(limit=50):
    """
    Skip the reconnect backoff, and stop the sender if it idles.

    Without the limit a regression does not fail the test, it hangs it: the
    sender that drops its batch goes back to polling an empty queue and never
    sends again, so the assertion is never reached.
    """
    calls = {'n': 0}

    async def sleep(_seconds):
        calls['n'] += 1
        if calls['n'] > limit:
            raise _StopSender()

    return sleep


class SenderProcessTests(SimpleTestCase):
    """
    The two ways the sender silently stopped delivering events.

    Both were found by reading the code rather than from a failure report, so
    these exist to keep them from coming back.
    """

    def _run(self, outcomes, queued, cookies_returned):
        queue = Queue()
        for event in queued:
            queue.put(event)
        sent = []
        cookies = []

        with patch(
            'agent.plugins.plugin_process_manager.get_session_cookie',
            side_effect=cookies_returned,
        ), patch(
            'agent.plugins.plugin_process_manager.websockets.connect',
            _fake_connect(outcomes, sent, cookies),
        ), patch(
            'agent.plugins.plugin_process_manager.asyncio.sleep',
            _no_sleep(),
        ):
            with self.assertRaises(_StopSender):
                sender_process(queue, {'tls': False}, {'username': 'a', 'password': 'b'})

        return sent, cookies

    def test_a_batch_that_fails_to_send_is_kept_for_the_next_connection(self):
        # The queue is drained before the send, so a batch dropped here is
        # gone. An indexer restart used to lose everything in flight.
        sent, _cookies = self._run(
            outcomes=[ConnectionResetError('indexer restarted'), _StopSender()],
            queued=[{'data': 'only event'}],
            cookies_returned=['first', 'second'],
        )

        self.assertEqual(len(sent), 2)
        self.assertEqual(json.loads(sent[0]), json.loads(sent[1]))
        self.assertEqual(json.loads(sent[1])[0]['data'], 'only event')

    def test_each_reconnect_authenticates_again(self):
        # Logging in once at startup meant an expired session produced an
        # endless reconnect loop with a cookie the indexer always rejects.
        _sent, cookies = self._run(
            outcomes=[ConnectionResetError('session expired'), _StopSender()],
            queued=[{'data': 'only event'}],
            cookies_returned=['first', 'second'],
        )

        self.assertEqual(cookies, ['sessionid=first', 'sessionid=second'])

    def test_giving_up_on_login_stops_rather_than_looping(self):
        queue = Queue()
        with patch(
            'agent.plugins.plugin_process_manager.get_session_cookie',
            return_value=None,
        ) as login, patch(
            'agent.plugins.plugin_process_manager.asyncio.sleep',
            _no_sleep(),
        ):
            sender_process(queue, {'tls': False}, {'username': 'a', 'password': 'b'})

        self.assertEqual(login.call_count, 5)

    def test_complete_batch_is_forwarded_as_typed_envelope_and_acknowledged(self):
        batch = {
            '_target': 'keycloak:realm-a',
            '_agent': {
                'agent_id': 'shipper-keycloak',
                'hostname': 'keycloak-0',
                'version': '1.0',
            },
            'agent_id': 'shipper-keycloak',
            'batch_id': 'batch-1',
            'cursor': 'cursor-1',
            'events': [{'index': 'keycloak', 'source': 'realm-a', 'value': 1}],
        }
        event_queue = Queue()
        event_queue.put(batch)
        ack_queue = Queue()
        sent = []
        responses = [
            {'type': 'resume_result', 'checkpoints': {'keycloak:realm-a': None}},
            {
                'type': 'ack',
                'target': 'keycloak:realm-a',
                'batch_id': 'batch-1',
                'cursor': 'cursor-1',
                'count': 1,
            },
        ]

        class Socket(_FakeWebSocket):
            async def recv(self):
                return json.dumps(responses.pop(0))

        class Connection:
            async def __aenter__(self):
                return Socket([None, None], sent)

            async def __aexit__(self, *_exc):
                return False

        with patch(
            'agent.plugins.plugin_process_manager.get_session_cookie',
            return_value='session',
        ), patch(
            'agent.plugins.plugin_process_manager.websockets.connect',
            return_value=Connection(),
        ), patch(
            'agent.plugins.plugin_process_manager.asyncio.sleep',
            _no_sleep(),
        ):
            with self.assertRaises(_StopSender):
                sender_process(
                    event_queue,
                    {'tls': False},
                    {'username': 'a', 'password': 'b'},
                    ack_queue,
                )

        resume, envelope = map(json.loads, sent)
        self.assertEqual(resume['type'], 'resume')
        self.assertEqual(envelope['type'], 'batch')
        self.assertEqual(envelope['target'], batch['_target'])
        self.assertNotIn('_target', envelope)
        self.assertNotIn('_agent', envelope)
        self.assertEqual(ack_queue.get_nowait()['status'], 'ack')

    def test_permanent_resume_nack_is_forwarded_instead_of_reconnected_forever(self):
        batch = {
            '_target': 'keycloak:realm-a',
            '_agent': {
                'agent_id': 'shipper-keycloak',
                'hostname': 'keycloak-0',
                'version': '1.0',
            },
            'agent_id': 'shipper-keycloak',
            'batch_id': 'batch-1',
            'cursor': 'cursor-1',
            'events': [{'index': 'keycloak', 'source': 'realm-a', 'value': 1}],
        }
        event_queue = Queue()
        event_queue.put(batch)
        ack_queue = Queue()
        sent = []

        class Socket(_FakeWebSocket):
            async def recv(self):
                return json.dumps({
                    'type': 'nack',
                    'error': 'agent_id_owned_by_another_user',
                    'retryable': False,
                })

        class Connection:
            async def __aenter__(self):
                return Socket([None], sent)

            async def __aexit__(self, *_exc):
                return False

        with patch(
            'agent.plugins.plugin_process_manager.get_session_cookie',
            return_value='session',
        ), patch(
            'agent.plugins.plugin_process_manager.websockets.connect',
            return_value=Connection(),
        ), patch(
            'agent.plugins.plugin_process_manager.asyncio.sleep',
            _no_sleep(),
        ):
            with self.assertRaises(_StopSender):
                sender_process(
                    event_queue,
                    {'tls': False},
                    {'username': 'a', 'password': 'b'},
                    ack_queue,
                )

        self.assertEqual(len(sent), 1)
        failure = ack_queue.get_nowait()
        self.assertEqual(failure['status'], 'nack')
        self.assertIs(failure['retryable'], False)
        self.assertEqual(failure['target'], batch['_target'])
        self.assertEqual(failure['batch_id'], batch['batch_id'])


class ExampleCheckpointedPlugin(CheckpointedPlugin):
    def collect_once(self, timestamp=None):
        return []


class CheckpointedPluginTests(SimpleTestCase):
    def setUp(self):
        self.event_queue = Queue(maxsize=2)
        self.ack_queue = Queue(maxsize=2)
        self.plugin = ExampleCheckpointedPlugin(
            {
                'agent_id': 'shipper-keycloak',
                'hostname': 'keycloak-0',
                'version': '1.0',
            },
            self.event_queue,
            self.ack_queue,
            Event(),
        )

    def test_build_batch_is_deterministic_and_owned_by_plugin(self):
        first = build_batch(
            agent=self.plugin.agent,
            target='keycloak:realm-a',
            cursor='cursor-1',
            events=[{'id': 'event-1'}],
            record_identities=['event-1'],
        )
        second = build_batch(
            agent=self.plugin.agent,
            target='keycloak:realm-a',
            cursor='cursor-1',
            events=[{'id': 'event-1'}],
            record_identities=['event-1'],
        )

        self.assertEqual(first, second)
        self.assertEqual(first['_target'], 'keycloak:realm-a')
        self.assertEqual(first['agent_id'], 'shipper-keycloak')

    def test_nack_requeues_the_identical_retained_batch(self):
        batch = build_batch(
            agent=self.plugin.agent,
            target='keycloak:realm-a',
            cursor='cursor-1',
            events=[{'id': 'event-1'}],
            record_identities=['event-1'],
        )
        self.ack_queue.put({
            'target': batch['_target'],
            'batch_id': batch['batch_id'],
            'status': 'nack',
            'retryable': True,
        })
        self.ack_queue.put({
            'target': batch['_target'],
            'batch_id': batch['batch_id'],
            'status': 'ack',
            'cursor': batch['cursor'],
        })

        with patch.object(self.plugin.stop_event, 'wait', return_value=False) as wait:
            acknowledgement = self.plugin.deliver_batch(batch, timeout=0.1)

        self.assertIs(self.event_queue.get_nowait(), batch)
        self.assertIs(self.event_queue.get_nowait(), batch)
        self.assertEqual(acknowledgement['status'], 'ack')
        self.assertEqual(
            self.plugin.acknowledged_positions['keycloak:realm-a'],
            'cursor-1',
        )
        wait.assert_called_once_with(1.0)

    def test_permanent_nack_emits_error_and_stops_target_without_retrying(self):
        batch = build_batch(
            agent=self.plugin.agent,
            target='keycloak:realm-a',
            cursor='cursor-1',
            events=[{'id': 'event-1'}],
            record_identities=['event-1'],
        )
        self.ack_queue.put({
            'target': batch['_target'],
            'batch_id': batch['batch_id'],
            'status': 'nack',
            'error': 'batch_id_reused',
            'retryable': False,
        })

        with self.assertRaisesRegex(PermanentDeliveryError, 'batch_id_reused'):
            self.plugin.deliver_batch(batch, timeout=0.1)

        self.assertIs(self.event_queue.get_nowait(), batch)
        status = self.event_queue.get_nowait()
        self.assertEqual(status['collection_state'], 'error')
        self.assertEqual(status['delivery_target'], 'keycloak:realm-a')
        self.assertTrue(self.event_queue.empty())
        self.assertEqual(
            self.plugin.failed_targets['keycloak:realm-a'],
            'batch_id_reused',
        )

    def test_late_ack_for_completed_batch_is_not_retained(self):
        batch = build_batch(
            agent=self.plugin.agent,
            target='keycloak:realm-a',
            cursor='cursor-1',
            events=[{'id': 'event-1'}],
            record_identities=['event-1'],
        )
        self.ack_queue.put({
            'target': batch['_target'],
            'batch_id': batch['batch_id'],
            'status': 'ack',
        })
        self.plugin.deliver_batch(batch, timeout=0.1)
        self.ack_queue.put({
            'target': batch['_target'],
            'batch_id': batch['batch_id'],
            'status': 'ack',
        })

        self.assertIsNone(
            self.plugin._next_acknowledgement('other-target', 'other-batch', 0.01)
        )
        self.assertEqual(self.plugin._ack_backlog, {})

    def test_queue_backpressure_blocks_instead_of_growing(self):
        queue = Queue(maxsize=1)
        queue.put({'already': 'full'})
        self.plugin.event_queue = queue
        batch = build_batch(
            agent=self.plugin.agent,
            target='keycloak:realm-a',
            cursor='cursor-1',
            events=[{'id': 'event-1'}],
            record_identities=['event-1'],
        )
        thread = Thread(target=self.plugin.enqueue_batch, args=(batch,))

        thread.start()
        thread.join(timeout=0.05)
        self.assertTrue(thread.is_alive())
        queue.get_nowait()
        thread.join(timeout=1)
        self.assertFalse(thread.is_alive())
        self.assertIs(queue.get_nowait(), batch)

    def test_sender_death_timeout_requeues_the_identical_batch(self):
        batch = build_batch(
            agent=self.plugin.agent,
            target='keycloak:realm-a',
            cursor='cursor-1',
            events=[{'id': 'event-1'}],
            record_identities=['event-1'],
        )
        result = []
        thread = Thread(
            target=lambda: result.append(self.plugin.deliver_batch(batch, timeout=0.05))
        )

        thread.start()
        dequeued_by_dead_sender = self.event_queue.get(timeout=1)
        replayed_for_new_sender = self.event_queue.get(timeout=1)
        self.assertIs(dequeued_by_dead_sender, batch)
        self.assertIs(replayed_for_new_sender, batch)
        self.ack_queue.put({
            'target': batch['_target'],
            'batch_id': batch['batch_id'],
            'status': 'ack',
            'cursor': batch['cursor'],
        })
        thread.join(timeout=1)

        self.assertFalse(thread.is_alive())
        self.assertEqual(result[0]['status'], 'ack')

    def test_collection_status_rejects_unknown_state(self):
        with self.assertRaisesRegex(ValueError, 'state'):
            collection_status('unknown', source='keycloak')

        status = collection_status('partial', source='keycloak', error='one realm failed')
        self.assertEqual(status['collection_state'], 'partial')
        self.assertEqual(status['collection_error'], 'one realm failed')

    def test_fetch_checkpoints_sends_resume_and_returns_server_cursors(self):
        sent = []

        class Socket:
            async def send(self, payload):
                sent.append(json.loads(payload))

            async def recv(self):
                return json.dumps({
                    'type': 'resume_result',
                    'checkpoints': {'keycloak:realm-a': 'cursor-1'},
                })

        class Connection:
            async def __aenter__(self):
                return Socket()

            async def __aexit__(self, *_exc):
                return False

        with patch(
            'agent.plugins.plugin_process_manager.authenticate',
            return_value='session',
        ), patch(
            'websockets.connect',
            return_value=Connection(),
        ):
            checkpoints = fetch_checkpoints(
                {'tls': False},
                {'username': 'a', 'password': 'b'},
                ['keycloak:realm-a'],
                self.plugin.agent,
            )

        self.assertEqual(checkpoints, {'keycloak:realm-a': 'cursor-1'})
        self.assertEqual(sent[0]['type'], 'resume')
        self.assertEqual(sent[0]['agent'], self.plugin.agent)


class WatchdogPluginTests(SimpleTestCase):
    def test_refuses_project_root_that_contains_log_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            base_dir = Path(directory)
            (base_dir / 'logs').mkdir()
            with override_settings(BASE_DIR=base_dir):
                with self.assertRaisesRegex(ValueError, 'overlaps'):
                    WatchdogPlugin(
                        {'path_to_watch': str(base_dir)},
                        Queue(),
                        Event(),
                    )

    def test_accepts_non_overlapping_watch_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            base_dir = Path(directory)
            watch_dir = base_dir / 'watched'
            watch_dir.mkdir()
            (base_dir / 'logs').mkdir()
            with override_settings(BASE_DIR=base_dir):
                plugin = WatchdogPlugin(
                    {'path_to_watch': str(watch_dir)},
                    Queue(),
                    Event(),
                )

        self.assertEqual(plugin.path, str(watch_dir.resolve()))

    def test_refuses_missing_watch_directory_without_creating_it(self):
        with tempfile.TemporaryDirectory() as directory:
            base_dir = Path(directory)
            (base_dir / 'logs').mkdir()
            watch_dir = base_dir / 'watched'
            with override_settings(BASE_DIR=base_dir):
                with self.assertRaisesRegex(ValueError, 'does not exist'):
                    WatchdogPlugin(
                        {'path_to_watch': str(watch_dir)},
                        Queue(),
                        Event(),
                    )

            self.assertFalse(watch_dir.exists())

    def test_agent_settings_disable_watchdog_with_explicit_path(self):
        with patch.dict('os.environ', {'DJANGO_SECRET_KEY': 'test-secret'}):
            from SIEMatic.settings.agent import AGENT

        watchdog_config = next(
            plugin for plugin in AGENT['plugins'] if plugin['name'] == 'watchdog'
        )
        self.assertFalse(watchdog_config['enabled'])
        self.assertTrue(watchdog_config['path_to_watch'])

        network_config = next(
            plugin
            for plugin in AGENT['plugins']
            if plugin['name'] == 'network_security'
        )
        self.assertTrue(network_config['enabled'])

        posture_config = next(
            plugin
            for plugin in AGENT['plugins']
            if plugin['name'] == 'host_security_posture'
        )
        self.assertTrue(posture_config['enabled'])


class HostSecurityPosturePluginTests(SimpleTestCase):
    def setUp(self):
        self.queue = Queue()
        self.stop_event = Event()
        self.plugin = HostSecurityPosturePlugin(
            {
                'host': 'test-host',
                'poll_interval': 900,
                'status_interval': 3600,
                'collect_local_accounts': False,
            },
            self.queue,
            self.stop_event,
        )

    def _drain(self):
        events = []
        while not self.queue.empty():
            events.append(self.queue.get_nowait())
        return events

    @patch.object(HostSecurityPosturePlugin, '_collect_security_controls')
    @patch.object(HostSecurityPosturePlugin, '_collect_filesystems')
    @patch.object(HostSecurityPosturePlugin, '_collect_user_sessions')
    @patch.object(HostSecurityPosturePlugin, '_collect_network_interfaces')
    @patch.object(HostSecurityPosturePlugin, '_collect_host_identity')
    def test_emits_json_serializable_initial_component_snapshots(
        self,
        host_identity,
        interfaces,
        sessions,
        filesystems,
        controls,
    ):
        host_identity.return_value = {'os': 'ExampleOS'}
        interfaces.return_value = [{'name': 'eth0', 'is_up': True}]
        sessions.return_value = [{'username': 'alice'}]
        filesystems.return_value = [{'mountpoint': '/'}]
        controls.return_value = {'firewall': {'state': 'enabled'}}

        self.plugin.collect_once(timestamp=1000.0)

        events = self._drain()
        self.assertEqual(
            [event['component'] for event in events[:-1]],
            [
                'host_identity',
                'network_interfaces',
                'user_sessions',
                'filesystems',
                'security_controls',
            ],
        )
        self.assertTrue(
            all(event['event_type'] == 'posture_snapshot' for event in events[:-1])
        )
        self.assertEqual(events[-1]['event_type'], 'collection_status')
        self.assertEqual(events[-1]['data']['state'], 'ok')
        json.dumps(events)

    @patch.object(HostSecurityPosturePlugin, '_collect_snapshot')
    def test_emits_only_changed_components_after_initial_snapshot(self, collect):
        collect.side_effect = [
            ({'host_identity': {'os': 'One'}, 'filesystems': []}, []),
            ({'host_identity': {'os': 'Two'}, 'filesystems': []}, []),
        ]

        self.plugin.collect_once(timestamp=1000.0)
        self._drain()
        self.plugin.collect_once(timestamp=1001.0)

        events = self._drain()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['event_type'], 'posture_changed')
        self.assertEqual(events[0]['component'], 'host_identity')
        self.assertEqual(events[0]['data'], {'os': 'Two'})
        self.assertEqual(events[0]['previous'], {'os': 'One'})

    @patch.object(HostSecurityPosturePlugin, '_collect_snapshot')
    def test_reports_partial_collection_without_discarding_good_data(self, collect):
        collect.return_value = (
            {'host_identity': {'os': 'ExampleOS'}},
            [{'component': 'local_accounts', 'error_type': 'AccessDenied'}],
        )

        self.plugin.collect_once(timestamp=1000.0)

        events = self._drain()
        self.assertEqual(events[0]['event_type'], 'posture_snapshot')
        self.assertEqual(events[1]['event_type'], 'collection_status')
        self.assertEqual(events[1]['data']['state'], 'partial')
        self.assertEqual(
            events[1]['data']['components_failed'],
            ['local_accounts'],
        )

    @patch('agent.plugins.host_security_posture_plugin.psutil.net_if_stats')
    @patch('agent.plugins.host_security_posture_plugin.psutil.net_if_addrs')
    def test_normalizes_network_interfaces(self, net_if_addrs, net_if_stats):
        net_if_addrs.return_value = {
            'eth0': [
                SimpleNamespace(
                    family=socket.AF_INET,
                    address='10.0.0.2',
                    netmask='255.255.255.0',
                    broadcast='10.0.0.255',
                    ptp=None,
                )
            ]
        }
        net_if_stats.return_value = {
            'eth0': SimpleNamespace(
                isup=True,
                duplex=psutil.NIC_DUPLEX_FULL,
                speed=1000,
                mtu=1500,
            )
        }

        interfaces = self.plugin._collect_network_interfaces()

        self.assertEqual(interfaces[0]['name'], 'eth0')
        self.assertEqual(interfaces[0]['duplex'], 'full')
        self.assertEqual(interfaces[0]['addresses'][0]['family'], 'ipv4')
        self.assertEqual(interfaces[0]['addresses'][0]['address'], '10.0.0.2')

    @patch.object(HostSecurityPosturePlugin, '_collect_windows_controls')
    @patch(
        'agent.plugins.host_security_posture_plugin.platform.system',
        return_value='Windows',
    )
    def test_dispatches_security_controls_by_platform(
        self,
        _system,
        windows_controls,
    ):
        windows_controls.return_value = {'firewall': {'state': 'available'}}

        result = self.plugin._collect_security_controls()

        self.assertEqual(result, windows_controls.return_value)
        windows_controls.assert_called_once_with()

    @patch.object(HostSecurityPosturePlugin, '_run')
    @patch(
        'agent.plugins.host_security_posture_plugin.shutil.which',
        return_value='/usr/sbin/ufw',
    )
    def test_linux_firewall_distinguishes_inactive_from_active(
        self,
        _which,
        run,
    ):
        run.return_value = 'Status: inactive'

        result = self.plugin._linux_firewall()

        self.assertEqual(result, {'provider': 'ufw', 'state': 'disabled'})

    @patch.object(HostSecurityPosturePlugin, '_run')
    @patch(
        'agent.plugins.host_security_posture_plugin.shutil.which',
        return_value='/usr/bin/lsblk',
    )
    def test_linux_disk_encryption_detects_nested_luks_devices(
        self,
        _which,
        run,
    ):
        run.return_value = json.dumps({
            'blockdevices': [
                {
                    'name': 'sda',
                    'type': 'disk',
                    'children': [
                        {
                            'name': 'sda2',
                            'type': 'part',
                            'fstype': 'crypto_LUKS',
                        }
                    ],
                }
            ]
        })

        result = self.plugin._linux_disk_encryption()

        self.assertEqual(result['state'], 'detected')
        self.assertEqual(result['encrypted_devices'], ['sda2'])

    def test_rejects_non_positive_intervals(self):
        with self.assertRaisesRegex(ValueError, 'command_timeout'):
            HostSecurityPosturePlugin(
                {'command_timeout': 0},
                self.queue,
                self.stop_event,
            )


class NetworkSecurityPluginTests(SimpleTestCase):
    def setUp(self):
        self.queue = Queue()
        self.stop_event = Event()
        self.plugin = NetworkSecurityPlugin(
            {
                'host': 'test-host',
                'poll_interval': 30,
                'status_interval': 300,
            },
            self.queue,
            self.stop_event,
        )

    @staticmethod
    def _connection(
        *,
        socket_type=socket.SOCK_STREAM,
        local=('0.0.0.0', 8080),
        remote=(),
        status=psutil.CONN_LISTEN,
        pid=123,
    ):
        return SimpleNamespace(
            family=socket.AF_INET,
            type=socket_type,
            laddr=local,
            raddr=remote,
            status=status,
            pid=pid,
        )

    @staticmethod
    def _process():
        process = Mock()
        process.name.return_value = 'example-server'
        process.exe.return_value = '/opt/example-server'
        process.username.return_value = 'service-user'
        process.cmdline.return_value = ['example-server', '--listen']
        return process

    def _drain(self):
        events = []
        while not self.queue.empty():
            events.append(self.queue.get_nowait())
        return events

    @patch('agent.plugins.network_security_plugin.psutil.Process')
    @patch('agent.plugins.network_security_plugin.psutil.net_connections')
    def test_collects_listeners_and_active_connections(
        self,
        net_connections,
        process,
    ):
        net_connections.return_value = [
            self._connection(),
            self._connection(
                local=('10.0.0.2', 50123),
                remote=('203.0.113.10', 443),
                status=psutil.CONN_ESTABLISHED,
            ),
        ]
        process.return_value = self._process()

        self.plugin.collect_once(timestamp=1000.0)

        events = self._drain()
        self.assertEqual(
            [event['event_type'] for event in events],
            ['listener_added', 'connection_opened', 'collection_status'],
        )
        listener = events[0]['data']
        self.assertEqual(listener['protocol'], 'tcp')
        self.assertEqual(listener['local_scope'], 'wildcard')
        self.assertEqual(listener['process_name'], 'example-server')
        self.assertIsNone(listener['process_cmdline'])
        connection = events[1]['data']
        self.assertEqual(connection['remote_address'], '203.0.113.10')
        self.assertEqual(connection['remote_port'], 443)
        self.assertEqual(events[2]['data']['state'], 'ok')
        process.assert_called_once_with(123)

    @patch('agent.plugins.network_security_plugin.psutil.Process')
    @patch('agent.plugins.network_security_plugin.psutil.net_connections')
    def test_emits_diffs_without_repeating_unchanged_sockets(
        self,
        net_connections,
        process,
    ):
        listener = self._connection()
        net_connections.return_value = [listener]
        process.return_value = self._process()

        self.plugin.collect_once(timestamp=1000.0)
        self._drain()
        self.plugin.collect_once(timestamp=1001.0)
        self.assertEqual(self._drain(), [])

        net_connections.return_value = []
        self.plugin.collect_once(timestamp=1002.0)
        events = self._drain()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['event_type'], 'listener_removed')

    @patch('agent.plugins.network_security_plugin.psutil.net_connections')
    def test_reports_collection_permission_failure(self, net_connections):
        net_connections.side_effect = psutil.AccessDenied(pid=1)

        self.plugin.collect_once(timestamp=1000.0)

        event = self.queue.get_nowait()
        self.assertEqual(event['event_type'], 'collection_status')
        self.assertEqual(event['data']['state'], 'error')
        self.assertIn('AccessDenied', event['data']['error'])

    @patch('agent.plugins.network_security_plugin.psutil.Process')
    @patch('agent.plugins.network_security_plugin.psutil.net_connections')
    def test_udp_socket_without_remote_endpoint_is_a_listener(
        self,
        net_connections,
        process,
    ):
        net_connections.return_value = [
            self._connection(
                socket_type=socket.SOCK_DGRAM,
                local=('127.0.0.1', 5353),
                status=psutil.CONN_NONE,
                pid=None,
            )
        ]

        self.plugin.collect_once(timestamp=1000.0)

        events = self._drain()
        self.assertEqual(events[0]['event_type'], 'listener_added')
        self.assertEqual(events[0]['data']['protocol'], 'udp')
        self.assertEqual(events[0]['data']['local_scope'], 'loopback')
        process.assert_not_called()

    def test_rejects_non_positive_intervals(self):
        with self.assertRaisesRegex(ValueError, 'poll_interval'):
            NetworkSecurityPlugin(
                {'poll_interval': 0},
                self.queue,
                self.stop_event,
            )
