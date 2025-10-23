
"""
Tests for the events app.

This module contains unit tests for event models, serializers, signals, and consumers.
Currently contains commented-out WebSocket consumer tests.
"""

# from django.test import TransactionTestCase
# from channels.testing import WebsocketCommunicator
# from SIEMatic.asgi import application
# from django.contrib.auth import get_user_model
# import json
# from agent.plugins.plugin_process_manager import get_session_cookie

# class EventConsumerTests(TransactionTestCase):
#     def setUp(self):
#         self.user = get_user_model().objects.create_user(username="testuser", password="testpass")

#     async def test_heartbeat_event(self):
#         # Setup login
#         indexer_cfg = {"host": "localhost", "port": 8000}
#         credentials = {"username": "testuser", "password": "testpass"}
#         sessionid = get_session_cookie(indexer_cfg, credentials)
#         headers = [(b'cookie', f'sessionid={sessionid}'.encode())] if sessionid else []
#         communicator = WebsocketCommunicator(application, "/indexer/", headers=headers)
#         connected, _ = await communicator.connect()
#         self.assertTrue(connected)
#         heartbeat = {"type": "heartbeat", "timestamp": 1234567890}
#         await communicator.send_json_to(heartbeat)
#         response = await communicator.receive_json_from()
#         self.assertEqual(response, heartbeat)
#         await communicator.disconnect()
