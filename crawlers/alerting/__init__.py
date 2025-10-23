"""
Alerting plugins for the crawlers app.
"""

import logging
logger = logging.getLogger(__name__)

# Registry of alerting plugins
alerting_plugins = {}

def register_alerting_plugin(name, plugin_class):
    """
    Register an alerting plugin.
    """
    alerting_plugins[name] = plugin_class
    logger.info(f"Registered alerting plugin: {name}")

def get_alerting_plugin(name):
    """
    Get a registered alerting plugin class by name.
    """
    return alerting_plugins.get(name)