"""
App configuration for the project app.

This module configures the project Django app.
"""

import logging
from django.apps import AppConfig


class ProjectConfig(AppConfig):
    """
    Configuration class for the project app.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'project'

    def ready(self):
        # Import signals to connect them
        import project.signals
