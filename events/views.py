"""
Views for the events app.

This module provides REST API views for Event models using Django REST framework.
"""

import logging
from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.response import Response
from django.conf import settings
from rest_framework.permissions import IsAuthenticated
from .models import Event
from .serializers import EventSerializer, EventBulkSerializer

logger = logging.getLogger(__name__)


class EventViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Event model operations.

    Provides CRUD operations for events with filtering, searching, and bulk creation support.
    """
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['index', 'sourcetype', 'source', 'host', 'created', 'updated']
    search_fields = ['index', 'sourcetype', 'source', 'host', 'created', 'updated', 'data', 'extracted_fields']

    def get_serializer(self, *args, **kwargs):
        """
        Get the appropriate serializer based on data type.

        Uses bulk serializer for list data.

        Returns:
            Serializer instance.
        """
        if isinstance(kwargs.get('data', {}), list):
            kwargs['many'] = True
            logger.debug("Using bulk serializer for list data")
            return EventBulkSerializer(*args, **kwargs)
        return super().get_serializer(*args, **kwargs)

    def create(self, request, *args, **kwargs):
        """
        Create one or more events.

        Handles both single and bulk event creation.

        Args:
            request: The HTTP request.

        Returns:
            Response with created event data.
        """
        data = request.data
        many = isinstance(data, list)
        logger.info(f"Creating {'bulk' if many else 'single'} event(s)")
        serializer = self.get_serializer(data=data, many=many)
        serializer.is_valid(raise_exception=True)
        events = serializer.save()
        event_count = len(events) if many else 1
        logger.info(f"Successfully created {event_count} event(s)")
        return Response(EventSerializer(events, many=many).data, status=status.HTTP_201_CREATED)
