"""
Serializers for the events app.

This module provides REST framework serializers for Event models,
including bulk creation support.
"""

import json
import logging
from rest_framework import serializers
from .extractors import apply_extractions
from .models import Event

logger = logging.getLogger(__name__)


class EventSerializer(serializers.ModelSerializer):
    """
    Serializer for individual Event instances.

    Handles serialization and creation of single events.
    """

    class Meta:
        model = Event
        fields = '__all__'

    def to_internal_value(self, data):
        """
        Accept ``data`` as either a string or a JSON object.

        ``Event.data`` is a text column, so a REST caller would otherwise have
        to encode the payload itself while the WebSocket path encodes it for
        them. Two payload shapes for one field is a trap for anyone writing a
        shipper, so encode an object or array here and store a string as-is.

        Args:
            data: The incoming request payload for one event.

        Returns:
            dict: Validated data with ``data`` guaranteed to be a string.
        """
        if isinstance(data, dict) and isinstance(data.get('data'), (dict, list)):
            data = {**data, 'data': json.dumps(data['data'])}
        return super().to_internal_value(data)

    def create(self, validated_data):
        """
        Create a single event instance.

        Args:
            validated_data: Validated data for event creation.

        Returns:
            Event: The created event instance.
        """
        event = Event.objects.create(**validated_data)
        logger.debug(f"Created single event with id {event.id}")
        return event


class BulkEventSerializer(serializers.ListSerializer):
    """
    List serializer for bulk event creation.

    Handles creation of multiple events in a single operation.
    """

    def create(self, validated_data):
        """
        Create multiple event instances in bulk.

        Args:
            validated_data: List of validated data for events.

        Returns:
            list: List of created event instances.
        """
        events = [
            apply_extractions(Event(**item))
            for item in validated_data
        ]
        created_events = Event.objects.bulk_create(events)
        logger.debug(f"Bulk created {len(created_events)} events")
        return created_events


class EventBulkSerializer(EventSerializer):
    """
    Serializer for bulk event operations.

    Uses the BulkEventSerializer for list operations.
    """

    class Meta(EventSerializer.Meta):
        list_serializer_class = BulkEventSerializer
