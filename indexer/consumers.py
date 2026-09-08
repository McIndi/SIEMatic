"""
WebSocket consumers for the indexer app.

This module handles WebSocket connections for event ingestion and indexing.
"""

import json
import hashlib
from collections import defaultdict

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class ProtocolError(ValueError):
    """A stable protocol error that is safe to return to a shipper."""


def canonical_digest(events):
    encoded = json.dumps(
        events,
        ensure_ascii=False,
        separators=(',', ':'),
        sort_keys=True,
    ).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


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
        return await database_sync_to_async(_bulk_create_events)(built_events)
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


def _build_event(event_data, *, strict_payload=False):
    """Build an unsaved Event and return it with its requested DB alias."""
    from events.models import Event

    event_data = _normalize_event_data(event_data)
    index = event_data.pop('index', 'default')
    source = event_data.pop('source', 'agent')
    host = event_data.pop('host', 'localhost')
    sourcetype = event_data.pop('sourcetype', 'json')
    db_alias = event_data.pop('db_alias', None) or 'default'
    normalized_sourcetype = str(sourcetype).lower()

    if not strict_payload:
        # Untyped agents predate the explicit data envelope. Preserve their
        # original serialization exactly, including TailPlugin's metadata.
        stored_data = json.dumps(event_data)
    elif normalized_sourcetype in {'logfmt', 'text'}:
        if set(event_data) != {'data'} or not isinstance(event_data['data'], str):
            raise ProtocolError('invalid_raw_payload')
        stored_data = event_data['data']
    elif normalized_sourcetype == 'json' and 'data' in event_data:
        if set(event_data) != {'data'}:
            raise ProtocolError('ambiguous_json_payload')
        data = event_data['data']
        stored_data = data if isinstance(data, str) else json.dumps(data)
    else:
        # Preserve the original flat JSON event shape for existing agents.
        stored_data = json.dumps(event_data)

    event = Event(
        index=index,
        source=source,
        host=host,
        sourcetype=sourcetype,
        data=stored_data,
    )
    return event, db_alias


def _bulk_create_events(built_events):
    """Persist a batch with one bulk insert per requested database alias."""
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
    await database_sync_to_async(event.save)(using=db_alias)
    logger.debug("Created event in database %s", db_alias)
    return event


def _resume_agent(user_id, agent_data, address, targets):
    from agent.models import Agent, Checkpoint

    agent_id = agent_data['agent_id']
    now = timezone.now()
    with transaction.atomic():
        agent = Agent.objects.select_for_update().filter(agent_id=agent_id).first()
        if agent is not None and agent.user_id not in (None, user_id):
            raise ProtocolError('agent_id_owned_by_another_user')
        if agent is None:
            agent = Agent(agent_id=agent_id, user_id=user_id)
        elif agent.user_id is None:
            agent.user_id = user_id
        agent.hostname = agent_data.get('hostname', '')
        agent.address = address
        agent.version = agent_data.get('version', '')
        agent.last_seen = now
        agent.save()

        stored = dict(
            Checkpoint.objects.filter(target__in=targets).values_list('target', 'cursor')
        )
    return agent.pk, {target: stored.get(target) for target in targets}


def _validate_and_build_typed_events(events):
    if not events:
        raise ProtocolError('empty_batch')

    built_events = []
    routing = set()
    for event_data in events:
        if not isinstance(event_data, dict):
            raise ProtocolError('invalid_event')
        event, db_alias = _build_event(event_data, strict_payload=True)
        if db_alias != 'default':
            raise ProtocolError('invalid_db_alias')
        routing.add((event.index, event.source))
        built_events.append((event, db_alias))

    if len(routing) != 1:
        raise ProtocolError('mixed_routing')
    index, source = routing.pop()
    return built_events, index, source


def _persist_typed_batch(agent_pk, payload):
    from agent.models import Agent, BatchReceipt, Checkpoint

    target = payload['target']
    batch_id = payload['batch_id']
    cursor = payload['cursor']
    events = payload['events']
    digest = canonical_digest(events)
    built_events, index, source = _validate_and_build_typed_events(events)
    now = timezone.now()

    with transaction.atomic(using='default'):
        receipt, created = BatchReceipt.objects.get_or_create(
            target=target,
            batch_id=batch_id,
            defaults={
                'cursor': cursor,
                'count': len(events),
                'content_digest': digest,
            },
        )
        if not created:
            if receipt.content_digest != digest or receipt.cursor != cursor:
                raise ProtocolError('batch_id_reused')
            Agent.objects.filter(pk=agent_pk).update(last_seen=now)
            return {
                'type': 'ack',
                'target': receipt.target,
                'batch_id': receipt.batch_id,
                'cursor': receipt.cursor,
                'count': receipt.count,
            }

        _bulk_create_events(built_events)
        if Agent.objects.filter(pk=agent_pk).update(
            events_delivered=F('events_delivered') + len(events),
            last_event_at=now,
            last_seen=now,
        ) != 1:
            raise ProtocolError('unknown_agent')
        Checkpoint.objects.update_or_create(
            target=target,
            create_defaults={
                'cursor': cursor,
                'agent_id': agent_pk,
                'index': index,
                'source': source,
                'events_delivered': len(events),
            },
            defaults={
                'cursor': cursor,
                'agent_id': agent_pk,
                'index': index,
                'source': source,
                'events_delivered': F('events_delivered') + len(events),
            },
        )

    return {
        'type': 'ack',
        'target': target,
        'batch_id': batch_id,
        'cursor': cursor,
        'count': len(events),
    }


def _touch_heartbeat_agents(payload, user_id):
    from agent.models import Agent

    items = payload if isinstance(payload, list) else [payload]
    agent_ids = {
        item.get('agent_id')
        for item in items
        if isinstance(item, dict)
        and item.get('type') == 'agent_heartbeat'
        and isinstance(item.get('agent_id'), str)
    }
    if agent_ids:
        Agent.objects.filter(
            user_id=user_id,
            agent_id__in=agent_ids,
        ).update(last_seen=timezone.now())


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
        authorized = bool(
            user
            and user.is_authenticated
            and await database_sync_to_async(user.has_perm)('events.add_event')
        )
        if authorized:
            logger.info("WebSocket connection accepted for user: %s", user.username)
            self.agent_id = None
            self.agent_pk = None
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
        if bytes_data is not None:
            await self.close(code=1003)
            return
        if not text_data:
            return

        max_message_bytes = getattr(settings, 'INDEXER_MAX_MESSAGE_BYTES', 1_048_576)
        if len(text_data.encode('utf-8')) > max_message_bytes:
            await self.close(code=1009)
            return

        try:
            payload = json.loads(text_data)
        except json.JSONDecodeError:
            await create_events(data=text_data)
            return

        if not isinstance(payload, dict) or 'type' not in payload:
            await create_events(data=payload)
            await database_sync_to_async(_touch_heartbeat_agents)(
                payload,
                self.scope['user'].pk,
            )
            return

        message_type = payload.get('type')
        try:
            if message_type == 'resume':
                await self._handle_resume(payload)
            elif message_type == 'batch':
                await self._handle_batch(payload)
            else:
                raise ProtocolError('unknown_message_type')
        except ProtocolError as exc:
            await self._send_nack(payload, str(exc), retryable=False)
        except Exception:
            logger.exception('Typed ingest failed')
            await self._send_nack(payload, 'write_failed', retryable=True)

    async def _handle_resume(self, payload):
        if self.agent_id is not None:
            raise ProtocolError('resume_already_received')
        agent_data = payload.get('agent')
        targets = payload.get('targets')
        if not isinstance(agent_data, dict) or not isinstance(targets, list):
            raise ProtocolError('invalid_resume')
        agent_id = agent_data.get('agent_id')
        if not isinstance(agent_id, str) or not agent_id or len(agent_id) > 255:
            raise ProtocolError('invalid_agent_id')
        max_targets = getattr(settings, 'INDEXER_MAX_RESUME_TARGETS', 100)
        if len(targets) > max_targets or any(
            not isinstance(target, str) or not target or len(target) > 512
            for target in targets
        ):
            raise ProtocolError('invalid_targets')

        client = self.scope.get('client') or (None, None)
        address = client[0]
        agent_pk, checkpoints = await database_sync_to_async(_resume_agent)(
            self.scope['user'].pk,
            agent_data,
            address,
            targets,
        )
        self.agent_id = agent_id
        self.agent_pk = agent_pk
        await self._send_json({
            'type': 'resume_result',
            'checkpoints': checkpoints,
        })

    async def _handle_batch(self, payload):
        if self.agent_id is None:
            raise ProtocolError('resume_required')
        if payload.get('agent_id') != self.agent_id:
            raise ProtocolError('agent_id_mismatch')

        target = payload.get('target')
        batch_id = payload.get('batch_id')
        cursor = payload.get('cursor')
        events = payload.get('events')
        max_events = getattr(settings, 'INDEXER_MAX_BATCH_EVENTS', 500)
        max_cursor = getattr(settings, 'INDEXER_MAX_CURSOR_LENGTH', 16_384)
        if not isinstance(target, str) or not target or len(target) > 512:
            raise ProtocolError('invalid_target')
        if not isinstance(batch_id, str) or not batch_id or len(batch_id) > 255:
            raise ProtocolError('invalid_batch_id')
        if not isinstance(cursor, str) or len(cursor) > max_cursor:
            raise ProtocolError('invalid_cursor')
        if not isinstance(events, list) or len(events) > max_events:
            raise ProtocolError('invalid_events')

        response = await database_sync_to_async(_persist_typed_batch)(
            self.agent_pk,
            payload,
        )
        await self._send_json(response)

    async def _send_nack(self, payload, error, *, retryable):
        response = {
            'type': 'nack',
            'error': error,
            'retryable': retryable,
        }
        for field in ('target', 'batch_id'):
            if isinstance(payload.get(field), str):
                response[field] = payload[field]
        await self._send_json(response)

    async def _send_json(self, payload):
        await self.send(text_data=json.dumps(payload, separators=(',', ':')))

