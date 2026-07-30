"""Tests for agent transport configuration."""

import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from agent.plugins.plugin_process_manager import get_indexer_transport
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
