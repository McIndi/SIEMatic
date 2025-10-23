"""
Test crawler plugin that always creates a finding on every run.
"""

import logging
from datetime import datetime
from .base import BaseCrawlerPlugin

logger = logging.getLogger(__name__)

class AlwaysFindingCrawler(BaseCrawlerPlugin):
    """
    Crawler that always creates a finding for testing alerts.
    """
    name = 'always_finding_crawler'

    def run(self):
        logger.info(f"Running {self.name} crawler")
        plugin_type = self.config.get('type', 'scheduled')
        if plugin_type == 'daemon':
            interval = self.config.get('interval', 60)
            while True:
                self._scan()
                import time
                time.sleep(interval)
        else:
            self._scan()

    def _scan(self):
        # Get the first event to link the finding to
        event = self.get_queryset().first()
        if not event:
            logger.warning("No events found, cannot create finding")
            return

        rule_name = 'always_finding_test'
        description = f"Test finding created at {datetime.now()}"
        severity = 'low'
        mitre_tactic = 'Test'
        mitre_technique = 'Test Technique'

        # No cooldown check for this test crawler
        self.create_finding(
            event=event,
            rule_name=rule_name,
            description=description,
            severity=severity,
            mitre_tactic=mitre_tactic,
            mitre_technique=mitre_technique,
        )
        logger.info(f"{self.name} crawler created test finding")