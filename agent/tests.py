"""Tests for agent transport configuration."""

import tempfile
import socket
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
from threading import Event
from unittest.mock import Mock, patch

import psutil

from django.test import SimpleTestCase, override_settings

from agent.plugins.plugin_process_manager import get_indexer_transport
from agent.plugins.network_security_plugin import NetworkSecurityPlugin
from agent.plugins.watchdog_plugin import WatchdogPlugin
from tools.gen_dev_cert import generate_certificate


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
