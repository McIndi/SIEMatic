"""
Plugins for the crawlers app.
"""

import logging
logger = logging.getLogger(__name__)

# Registry of crawler plugins
crawler_plugins = {}

def register_plugin(name, plugin_class):
    """
    Register a crawler plugin.
    """
    crawler_plugins[name] = plugin_class
    logger.info(f"Registered crawler plugin: {name}")

def get_plugin(name):
    """
    Get a registered plugin class by name.
    """
    return crawler_plugins.get(name)