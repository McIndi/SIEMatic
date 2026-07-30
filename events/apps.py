"""
App configuration for the events app.

This module configures the events Django app.
"""

from django.apps import AppConfig


class EventsConfig(AppConfig):
    """Configuration class for the events app."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'events'
