"""
Tests for the indexer app.

This module contains unit tests for indexer models, consumers, and routing.
"""
import json
import tempfile
from pathlib import Path
import sys

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase, TestCase

from events.models import Event
from indexer.consumers import (
    EventConsumer,
    _build_event,
    _bulk_create_events,
    create_events,
)
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


class WebSocketBatchIngestTests(TestCase):
    def test_batch_uses_one_insert_and_extracts_all_events(self):
        built_events = [
            _build_event({'sequence': sequence})
            for sequence in range(3)
        ]

        with self.assertNumQueries(1):
            events = _bulk_create_events(built_events)

        self.assertEqual(len(events), 3)
        self.assertEqual(Event.objects.count(), 3)
        self.assertEqual(
            [event.extracted_fields['sequence'] for event in events],
            [0, 1, 2],
        )

    def test_malformed_batch_item_does_not_drop_other_events(self):
        events = async_to_sync(create_events)(
            json.dumps([
                {'sequence': 1},
                'not-json',
                {'sequence': 3},
            ])
        )

        self.assertEqual(len(events), 3)
        self.assertEqual(Event.objects.count(), 3)
        self.assertEqual(events[1].extracted_fields, {'data': 'not-json'})


class WebSocketAuthenticationTests(TestCase):
    def test_authenticated_connection_is_accepted(self):
        user = get_user_model().objects.create_user(username="agent")

        async def exercise_connection():
            communicator = WebsocketCommunicator(
                EventConsumer.as_asgi(),
                "/indexer/",
            )
            communicator.scope["user"] = user
            connected, _ = await communicator.connect()
            if connected:
                await communicator.disconnect()
            return connected

        self.assertTrue(async_to_sync(exercise_connection)())

    def test_anonymous_connection_is_rejected(self):
        communicator = WebsocketCommunicator(
            EventConsumer.as_asgi(),
            "/indexer/",
        )
        communicator.scope["user"] = AnonymousUser()

        connected, _ = async_to_sync(communicator.connect)()

        self.assertFalse(connected)
