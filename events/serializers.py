"""
Serializers for the events app.

This module provides REST framework serializers for Event models,
including bulk creation support.
"""

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
