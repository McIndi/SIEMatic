"""
Base class for crawler plugins.
"""

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class BaseCrawlerPlugin(ABC):
    """
    Abstract base class for crawler plugins.
    Plugins should inherit from this and implement the run method.
    """

    def __init__(self, config=None):
        self.config = config or {}
        self.name = self.config.get('name', self.__class__.__name__)

    @abstractmethod
    def run(self):
        """
        Run the crawler logic.
        For daemon mode, should loop continuously.
        For scheduled, run once.
        """
        raise NotImplementedError("Subclasses must implement the run method")

    def get_queryset(self, model_class=None, **filters):
        """
        Helper to get a queryset from the configured database.
        """
        from events.models import Event
        model = model_class or Event
        db_alias = self.config.get('db_alias', 'default')
        return model.objects.using(db_alias).filter(**filters)

    def create_finding(self, event, rule_name, description, severity='medium', mitre_tactic=None, mitre_technique=None):
        """
        Create a finding for an event.
        Checks for cooldown based on config before creating.
        """
        from crawlers.models import Finding
        cooldown = self.config.get('realert_cooldown')
        if not Finding.can_create_finding(event, rule_name, cooldown):
            logger.debug("Skipping finding creation due to cooldown: %s for event %s", rule_name, event.id)
            return None
        
        finding = Finding.objects.create(
            event=event,
            rule_name=rule_name,
            description=description,
            severity=severity,
            mitre_tactic=mitre_tactic,
            mitre_technique=mitre_technique,
        )
        logger.info("Created finding: %s", finding)
        self.send_alerts(finding)
        return finding

    def send_alerts(self, finding):
        """
        Send alerts for the finding using configured alerting plugins.
        """
        alerting_plugins = self.config.get('alerting_plugins', [])
        if not alerting_plugins:
            return
        from django.conf import settings
        alerting_plugin_paths = getattr(settings, 'ALERTING_PLUGINS', [])
        alerting_configs = getattr(settings, 'ALERTING_CONFIGS', {})
        # Load plugin classes if not already
        if not hasattr(self, '_alerting_classes'):
            import importlib
            self._alerting_classes = {}
            for plugin_path in alerting_plugin_paths:
                try:
                    module_path, class_name = plugin_path.rsplit('.', 1)
                    module = importlib.import_module(module_path)
                    plugin_class = getattr(module, class_name)
                    name = getattr(plugin_class, 'name', class_name.lower())
                    self._alerting_classes[name] = plugin_class
                except Exception as e:
                    logger.error(f"Failed to load alerting plugin {plugin_path}: {e}")
        for plugin_name in alerting_plugins:
            if plugin_name in self._alerting_classes:
                config = alerting_configs.get(plugin_name, {})
                plugin_instance = self._alerting_classes[plugin_name](config)
                try:
                    plugin_instance.send_alert(finding)
                except Exception as e:
                    logger.error(f"Failed to send alert with {plugin_name}: {e}")
            else:
                logger.warning(f"Alerting plugin {plugin_name} not loaded")