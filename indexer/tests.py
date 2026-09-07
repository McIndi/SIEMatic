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
from django.contrib.auth.models import AnonymousUser, Permission
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from unittest.mock import patch

from agent.models import Agent, BatchReceipt, Checkpoint
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
        user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label='events',
                codename='add_event',
            )
        )

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

    def test_authenticated_user_without_add_event_is_rejected(self):
        user = get_user_model().objects.create_user(username='viewer')

        async def exercise_connection():
            communicator = WebsocketCommunicator(EventConsumer.as_asgi(), '/indexer/')
            communicator.scope['user'] = user
            connected, _ = await communicator.connect()
            return connected

        self.assertFalse(async_to_sync(exercise_connection)())


class CheckpointProtocolTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.user = get_user_model().objects.create_user(username='shipper')
        self.user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label='events',
                codename='add_event',
            )
        )
        self.resume = {
            'type': 'resume',
            'agent': {
                'agent_id': 'shipper-keycloak',
                'hostname': 'keycloak-0',
                'version': '1.0',
            },
            'targets': ['keycloak:realm-a'],
        }
        self.batch = {
            'type': 'batch',
            'agent_id': 'shipper-keycloak',
            'target': 'keycloak:realm-a',
            'batch_id': 'batch-1',
            'cursor': '{"time":1,"ids":["event-1"]}',
            'events': [
                {
                    'index': 'keycloak',
                    'source': 'realm-a',
                    'host': 'keycloak-0',
                    'sourcetype': 'keycloak:event',
                    'event_id': 'event-1',
                },
            ],
        }

    async def _connect(self):
        communicator = WebsocketCommunicator(EventConsumer.as_asgi(), '/indexer/')
        communicator.scope['user'] = self.user
        communicator.scope['client'] = ('192.0.2.10', 4321)
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        return communicator

    def test_permitted_legacy_batch_still_ingests_without_reply(self):
        async def exercise():
            communicator = await self._connect()
            await communicator.send_json_to([{'sequence': 1}])
            self.assertTrue(await communicator.receive_nothing(timeout=0.05))
            await communicator.disconnect()

        async_to_sync(exercise)()
        self.assertEqual(Event.objects.count(), 1)

    def test_batch_must_follow_resume_and_match_bound_agent(self):
        async def exercise():
            communicator = await self._connect()
            await communicator.send_json_to(self.batch)
            before_resume = await communicator.receive_json_from()
            await communicator.send_json_to(self.resume)
            await communicator.receive_json_from()
            wrong_agent = dict(self.batch, agent_id='somebody-else')
            await communicator.send_json_to(wrong_agent)
            mismatch = await communicator.receive_json_from()
            await communicator.disconnect()
            return before_resume, mismatch

        before_resume, mismatch = async_to_sync(exercise)()
        self.assertEqual(before_resume['type'], 'nack')
        self.assertEqual(before_resume['error'], 'resume_required')
        self.assertEqual(mismatch['type'], 'nack')
        self.assertEqual(mismatch['error'], 'agent_id_mismatch')
        self.assertEqual(Event.objects.count(), 0)

    def test_resume_binds_identity_and_returns_checkpoints(self):
        Checkpoint.objects.create(
            target='keycloak:realm-a',
            cursor='stored-cursor',
            index='keycloak',
            source='realm-a',
        )

        async def exercise():
            communicator = await self._connect()
            await communicator.send_json_to(self.resume)
            response = await communicator.receive_json_from()
            await communicator.disconnect()
            return response

        response = async_to_sync(exercise)()
        self.assertEqual(
            response,
            {'type': 'resume_result', 'checkpoints': {'keycloak:realm-a': 'stored-cursor'}},
        )
        agent = Agent.objects.get(agent_id='shipper-keycloak')
        self.assertEqual(agent.user, self.user)
        self.assertEqual(agent.address, '192.0.2.10')

    def test_resume_cannot_claim_another_users_agent(self):
        owner = get_user_model().objects.create_user(username='owner')
        Agent.objects.create(agent_id='shipper-keycloak', user=owner)

        async def exercise():
            communicator = await self._connect()
            await communicator.send_json_to(self.resume)
            response = await communicator.receive_json_from()
            await communicator.disconnect()
            return response

        response = async_to_sync(exercise)()
        self.assertEqual(response['type'], 'nack')
        self.assertEqual(response['error'], 'agent_id_owned_by_another_user')

    def test_batch_commit_is_atomic_and_retryable(self):
        async def exercise():
            communicator = await self._connect()
            await communicator.send_json_to(self.resume)
            await communicator.receive_json_from()
            with patch('indexer.consumers._bulk_create_events', side_effect=RuntimeError('db down')):
                await communicator.send_json_to(self.batch)
                failed = await communicator.receive_json_from()
            await communicator.send_json_to(self.batch)
            retried = await communicator.receive_json_from()
            await communicator.disconnect()
            return failed, retried

        failed, retried = async_to_sync(exercise)()
        self.assertEqual(failed['type'], 'nack')
        self.assertEqual(retried['type'], 'ack')
        self.assertEqual(retried['count'], 1)
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(BatchReceipt.objects.count(), 1)
        checkpoint = Checkpoint.objects.get(target='keycloak:realm-a')
        self.assertEqual(checkpoint.events_delivered, 1)
        agent = Agent.objects.get(agent_id='shipper-keycloak')
        self.assertEqual(agent.events_delivered, 1)
        self.assertIsNotNone(agent.last_event_at)

    def test_duplicate_batch_returns_identical_ack_without_duplicate_events(self):
        async def exercise():
            communicator = await self._connect()
            await communicator.send_json_to(self.resume)
            await communicator.receive_json_from()
            await communicator.send_json_to(self.batch)
            first = await communicator.receive_json_from()
            await communicator.send_json_to(self.batch)
            second = await communicator.receive_json_from()
            await communicator.disconnect()
            return first, second

        first, second = async_to_sync(exercise)()
        self.assertEqual(first, second)
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(Checkpoint.objects.get().events_delivered, 1)
        self.assertEqual(Agent.objects.get().events_delivered, 1)

    def test_reused_batch_id_with_changed_cursor_is_rejected(self):
        async def exercise():
            communicator = await self._connect()
            await communicator.send_json_to(self.resume)
            await communicator.receive_json_from()
            await communicator.send_json_to(self.batch)
            await communicator.receive_json_from()
            await communicator.send_json_to(dict(self.batch, cursor='different-cursor'))
            response = await communicator.receive_json_from()
            await communicator.disconnect()
            return response

        response = async_to_sync(exercise)()
        self.assertEqual(response['type'], 'nack')
        self.assertEqual(response['error'], 'batch_id_reused')
        self.assertEqual(Event.objects.count(), 1)

    def test_different_batch_ids_with_same_content_both_land(self):
        async def exercise():
            communicator = await self._connect()
            await communicator.send_json_to(self.resume)
            await communicator.receive_json_from()
            await communicator.send_json_to(self.batch)
            await communicator.receive_json_from()
            await communicator.send_json_to(dict(self.batch, batch_id='batch-2'))
            response = await communicator.receive_json_from()
            await communicator.disconnect()
            return response

        response = async_to_sync(exercise)()
        self.assertEqual(response['type'], 'ack')
        self.assertEqual(Event.objects.count(), 2)
        self.assertEqual(BatchReceipt.objects.count(), 2)
        self.assertEqual(Checkpoint.objects.get().events_delivered, 2)

    @override_settings(INDEXER_MAX_MESSAGE_BYTES=128)
    def test_oversized_message_is_closed(self):
        async def exercise():
            communicator = await self._connect()
            await communicator.send_to(text_data=json.dumps({'padding': 'x' * 256}))
            response = await communicator.receive_output()
            return response

        response = async_to_sync(exercise)()
        self.assertEqual(response['type'], 'websocket.close')
        self.assertEqual(Event.objects.count(), 0)
