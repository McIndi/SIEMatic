"""Tests for agent transport configuration."""

import tempfile
import socket
import json
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
from threading import Event
from unittest.mock import Mock, patch

import psutil

from django.test import SimpleTestCase, override_settings

from agent.plugins.plugin_process_manager import get_indexer_transport
from agent.plugins.host_security_posture_plugin import HostSecurityPosturePlugin
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
