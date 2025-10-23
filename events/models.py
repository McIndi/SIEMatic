"""
Models for the events app.

This module defines the Event model for storing indexed event data
with metadata and extracted fields.
"""

import logging
from django.db import models

logger = logging.getLogger(__name__)


class Event(models.Model):
    """
    Model representing an indexed event.

    Stores event data along with metadata like index, sourcetype, source, and host.
    Includes extracted fields for structured data access.
    """
    id = models.BigAutoField(primary_key=True)
    index = models.CharField(max_length=255, default="default", db_index=True)
    sourcetype = models.CharField(max_length=255, default="default", db_index=True)
    source = models.CharField(max_length=255, default="default", db_index=True)
    host = models.CharField(max_length=255, default="default", db_index=True)
    data = models.TextField()
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    updated = models.DateTimeField(auto_now=True, db_index=True)
    extracted_fields = models.JSONField(default=dict, blank=True, null=True)

    def __str__(self):
        """
        String representation of the event.

        Returns a truncated view of the event metadata and data.
        """
        return f"{self.host}: {self.index}: {self.source}: {self.sourcetype}: {self.data[:25]}...{self.data[-25:]}"
