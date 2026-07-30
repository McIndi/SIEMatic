"""
Views for the events app.

This module provides REST API views for Event models using Django REST framework.
"""

import logging
from rest_framework import permissions, status, viewsets
from rest_framework.response import Response
from .models import Event
from .serializers import EventSerializer, EventBulkSerializer

logger = logging.getLogger(__name__)


class EventModelPermissions(permissions.DjangoModelPermissions):
    perms_map = {
        'GET': ['%(app_label)s.view_%(model_name)s'],
        'OPTIONS': ['%(app_label)s.view_%(model_name)s'],
        'HEAD': ['%(app_label)s.view_%(model_name)s'],
        'POST': ['%(app_label)s.add_%(model_name)s'],
        'PUT': ['%(app_label)s.change_%(model_name)s'],
        'PATCH': ['%(app_label)s.change_%(model_name)s'],
        'DELETE': ['%(app_label)s.delete_%(model_name)s'],
    }


class EventViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Event model operations.

    Provides CRUD operations for events with filtering, searching, and bulk creation support.
    """
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    permission_classes = [EventModelPermissions]
    throttle_scope = 'ingest'
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
