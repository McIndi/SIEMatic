"""Tests for agent transport configuration."""

import tempfile
from pathlib import Path
from queue import Queue
from threading import Event
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from agent.plugins.plugin_process_manager import get_indexer_transport
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
