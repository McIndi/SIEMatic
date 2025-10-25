"""
Example crawler plugin: Detects failed login attempts.
"""

import logging
import time
from datetime import timedelta
from django.utils import timezone
from .base import BaseCrawlerPlugin

logger = logging.getLogger(__name__)

class FailedLoginCrawler(BaseCrawlerPlugin):
    """
    Crawler that detects failed login events.
    Looks for events containing 'failed login' in the data field.
    """
    name = 'failed_login_crawler'

    def run(self):
        logger.info(f"Running {self.name} crawler")
        plugin_type = self.config.get('type', 'scheduled')
        if plugin_type == 'daemon':
            interval = self.config.get('interval', 60)
            while True:
                self._scan()
                time.sleep(interval)
        else:
            self._scan()

    def _scan(self):
        # Limit to events created within 1.5x the interval ago
        interval = self.config.get('interval', 60)
        since = timezone.now() - timedelta(seconds=interval * 1.5)
        # Query events with 'failed login' in data, created since then
        queryset = self.get_queryset().filter(data__icontains='failed login', created__gte=since)
        cooldown = self.config.get('realert_cooldown')
        for event in queryset:
            # Check if finding already exists for this event and rule within cooldown
            from crawlers.models import Finding
            query = Finding.objects.filter(event=event, rule_name=self.name)
            if cooldown:
                cooldown_since = timezone.now() - timedelta(seconds=cooldown)
                query = query.filter(created__gte=cooldown_since)
            if query.exists():
                continue  # Skip re-alerting
            self.create_finding(
                event=event,
                rule_name=self.name,
                description=f"Failed login detected in event data: {event.data[:100]}...",
                severity='medium',
                mitre_tactic='Credential Access',
                mitre_technique='Brute Force',
            )
        logger.info(f"{self.name} crawler scan completed")
