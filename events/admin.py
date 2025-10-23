"""
Admin configuration for the events app.

This module registers the Event model with the Django admin interface,
providing a customized admin view for event management.
"""

import logging
from django.contrib import admin

from .models import Event

logger = logging.getLogger(__name__)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    """
    Admin interface for the Event model.

    Provides list display, search, filtering, and readonly fields for event inspection.
    """
    list_display = ('id', 'index', 'sourcetype', 'source', 'host', 'created', 'updated')
    search_fields = ('index', 'sourcetype', 'source', 'host', 'data')
    list_filter = ('index', 'sourcetype', 'source', 'host', 'created', 'updated')
    readonly_fields = ('data', 'created', 'updated', 'extracted_fields')
    ordering = ('-created',)
