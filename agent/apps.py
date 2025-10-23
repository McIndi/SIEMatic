"""
AppConfig for the agent app.
Handles application configuration and setup.
"""

import logging
logger = logging.getLogger(__name__)
logger.debug("agent.apps module loaded.")

from django.apps import AppConfig


class AgentConfig(AppConfig):
    """
    Configuration for the agent Django app.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'agent'
