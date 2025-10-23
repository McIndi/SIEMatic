"""
WebSocket consumers for the indexer app.

This module handles WebSocket connections for event ingestion and indexing.
"""

import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
import logging

logger = logging.getLogger(__name__)


async def create_events(data):
    """
    Create events from incoming data.

    Parses data as JSON if possible. If it's a list, creates multiple events.

    Args:
        data: The raw data to create events from.
    """
    from events.models import Event
    # If data is a string, try to parse as JSON
    if isinstance(data, str):
        try:
            parsed_data = json.loads(data)
            logger.debug("Parsed data as JSON")
        except Exception as e:
            logger.debug(f"Failed to parse data as JSON: {e}, treating as raw string")
            parsed_data = {'data': data}
    else:
        parsed_data = data

    # If parsed_data is a list, process each item
    if isinstance(parsed_data, list):
        events = []
        for event_data in parsed_data:
            event = await _create_single_event(event_data)
            events.append(event)
        return events
    else:
        # Single event
        return [await _create_single_event(parsed_data)]


async def _create_single_event(event_data):
    """
    Create a single event from event_data dict.
    """
    from events.models import Event
    index = event_data.pop('index', 'default')
    source = event_data.pop('source', 'agent')
    host = event_data.pop('host', 'localhost')
    sourcetype = event_data.pop('sourcetype', 'json')
    db_alias = event_data.pop('db_alias', None)
    # Store all other fields as data
    data_field = json.dumps(event_data)

    create_kwargs = dict(
        index=index,
        source=source,
        host=host,
        sourcetype=sourcetype,
        data=data_field
    )
    if db_alias:
        event = await sync_to_async(Event.objects.using(db_alias).create)(**create_kwargs)
        logger.debug(f"Created event in database {db_alias}")
    else:
        event = await sync_to_async(Event.objects.create)(**create_kwargs)
        logger.debug("Created event in default database")
    return event


class EventConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for event ingestion.

    Handles authenticated WebSocket connections and creates events from received data.
    """

    async def connect(self):
        """
        Handle WebSocket connection.

        Accepts connection if user is authenticated, otherwise closes.
        """
        logger.info("WebSocket connection requested.")
        user = self.scope.get("user")
        if user and user.is_authenticated:
            logger.info("WebSocket connection accepted for user: %s", user.username)
            await self.accept()
        else:
            logger.warning("WebSocket connection rejected for user: %s", getattr(user, 'username', 'Anonymous'))
            await self.close()

    async def disconnect(self, code):
        """
        Handle WebSocket disconnection.

        Args:
            code: The disconnection code.
        """
        logger.info("WebSocket disconnected with code: %s", code)

    async def receive(self, text_data=None, bytes_data=None):
        """
        Handle received WebSocket data.

        Creates events from the received text data (single or batch).

        Args:
            text_data: The text data received.
            bytes_data: The bytes data received (ignored).
        """
        from events.models import Event

        logger.debug("WebSocket received len(text_data): %s, len(bytes_data): %s", len(text_data or ''), len(bytes_data or b''))
        if text_data:
            await create_events(data=text_data)

