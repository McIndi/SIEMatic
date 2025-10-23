"""
App configuration for the indexer app.

This module configures the indexer Django app.
"""

import logging
from django.apps import AppConfig


class IndexerConfig(AppConfig):
    """
    Configuration class for the indexer app.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'indexer'
