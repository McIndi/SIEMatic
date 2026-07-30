"""
Tests for the indexer app.

This module contains unit tests for indexer models, consumers, and routing.
"""
import tempfile
from pathlib import Path
import sys

from django.test import SimpleTestCase

from indexer.management.commands.indexer import build_daphne_command
from tools.gen_dev_cert import generate_certificate


class DaphneCommandTests(SimpleTestCase):
    def test_plain_endpoint_uses_bind_and_port(self):
        command = build_daphne_command(sys.executable, '127.0.0.1', '5001')

        self.assertIn('-b', command)
        self.assertIn('-p', command)
        self.assertNotIn('-e', command)

    def test_tls_endpoint_uses_certificate_and_key(self):
        with tempfile.TemporaryDirectory() as directory:
            cert = Path(directory) / 'indexer.crt'
            key = Path(directory) / 'indexer.key'
            generate_certificate(cert, key, ['localhost'])
            command = build_daphne_command(
                sys.executable, '127.0.0.1', '5001', cert, key
            )

        endpoint = command[command.index('-e') + 1]
        self.assertTrue(endpoint.startswith('ssl:5001:'))
        self.assertIn('privateKey=', endpoint)
        self.assertIn('certKey=', endpoint)
        self.assertNotIn('-b', command)

    def test_partial_tls_configuration_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'must either both be set'):
            build_daphne_command(
                sys.executable, '127.0.0.1', '5001', 'cert.pem', None
            )
