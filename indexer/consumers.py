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
        built_events = [_build_event(event_data) for event_data in parsed_data]
        return await sync_to_async(_bulk_create_events)(built_events)
    else:
        # Single event
        return [await _create_single_event(parsed_data)]


def _normalize_event_data(event_data):
    """Return one event payload as a dictionary without mutating the input."""
    if isinstance(event_data, str):
        try:
            event_data = json.loads(event_data)
        except (TypeError, json.JSONDecodeError) as exc:
            logger.debug(
                "Failed to parse batch item as JSON: %s; treating as raw data",
                exc,
            )
            return {'data': event_data}
    if not isinstance(event_data, dict):
        return {'data': event_data}
    return event_data.copy()


def _build_event(event_data):
    """Build an unsaved Event and return it with its requested DB alias."""
    from events.models import Event

    event_data = _normalize_event_data(event_data)
    index = event_data.pop('index', 'default')
    source = event_data.pop('source', 'agent')
    host = event_data.pop('host', 'localhost')
    sourcetype = event_data.pop('sourcetype', 'json')
    db_alias = event_data.pop('db_alias', None) or 'default'
    event = Event(
        index=index,
        source=source,
        host=host,
        sourcetype=sourcetype,
        data=json.dumps(event_data),
    )
    return event, db_alias


def _bulk_create_events(built_events):
    """Persist a batch with one bulk insert per requested database alias."""
    from collections import defaultdict
    from events.extractors import apply_extractions
    from events.models import Event

    events_by_alias = defaultdict(list)
    for event, db_alias in built_events:
        events_by_alias[db_alias].append(apply_extractions(event))

    for db_alias, events in events_by_alias.items():
        Event.objects.using(db_alias).bulk_create(events)
        logger.debug(
            "Bulk created %d events in database %s", len(events), db_alias
        )
    return [event for event, _db_alias in built_events]


async def _create_single_event(event_data):
    """
    Create a single event from event_data dict.
    """
    event, db_alias = _build_event(event_data)
    await sync_to_async(event.save)(using=db_alias)
    logger.debug("Created event in database %s", db_alias)
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
        logger.debug("WebSocket received len(text_data): %s, len(bytes_data): %s", len(text_data or ''), len(bytes_data or b''))
        if text_data:
            await create_events(data=text_data)

