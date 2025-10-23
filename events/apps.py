"""
App configuration for the events app.

This module configures the events Django app and imports signals on app ready.
"""

import logging
from django.apps import AppConfig

logger = logging.getLogger(__name__)


class EventsConfig(AppConfig):
    """
    Configuration class for the events app.

    Imports event signals when the app is ready.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'events'

    def ready(self):
        """
        Perform initialization tasks when the app is ready.

        Imports event signals to enable signal handling.
        """
        import events.signals
        logger.debug("Imported events.signals")
