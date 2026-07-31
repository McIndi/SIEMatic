"""
Crawler plugin for data retention: Deletes events older than a specified age.
"""

import logging
from datetime import timedelta
from django.utils import timezone
from crawlers.models import Finding
from events.models import Event
from .base import BaseCrawlerPlugin

logger = logging.getLogger(__name__)

class DataRetentionCrawler(BaseCrawlerPlugin):
    """
    Crawler that enforces data retention policies by deleting old events.
    """
    name = 'data_retention_crawler'

    def get_deletable_queryset(self, **filters):
        """Return matching events that have no actionable findings."""
        return self.get_queryset().filter(**filters).exclude(
            findings__status__in=Finding.actionable_statuses(),
        )

    @staticmethod
    def deletion_counts(queryset):
        """Delete a queryset and return separate event and finding counts."""
        _, deleted_by_model = queryset.delete()
        return (
            deleted_by_model.get(Event._meta.label, 0),
            deleted_by_model.get(Finding._meta.label, 0),
        )

    def run(self):
        logger.info(f"Running {self.name} crawler")
        try:
            retention_days = self.config.get('retention_days', 90)
            threshold = timezone.now() - timedelta(days=retention_days)
            rules = self.config.get('rules', [])
            
            if not rules:
                # Fallback to old config for backward compatibility
                split_by_field = self.config.get('split_by_field')
                allow_list = self.config.get('allow_list', [])
                deny_list = self.config.get('deny_list', [])
                rules = [{'split_by': split_by_field, 'allow': allow_list, 'deny': deny_list}] if split_by_field else []
            
            total_events_deleted = 0
            total_findings_deleted = 0
            for rule in rules:
                split_by = rule.get('split_by')
                allow = rule.get('allow', [])
                deny = rule.get('deny', [])
                
                if split_by:
                    # Get distinct values for the split field, filtered by allow/deny
                    distinct_values = self.get_queryset().values_list(split_by, flat=True).distinct()
                    if allow:
                        distinct_values = [v for v in distinct_values if v in allow]
                    if deny:
                        distinct_values = [v for v in distinct_values if v not in deny]
                    
                    for value in distinct_values:
                        filter_kwargs = {split_by: value, 'created__lt': threshold}
                        events_deleted, findings_deleted = self.deletion_counts(
                            self.get_deletable_queryset(**filter_kwargs),
                        )
                        total_events_deleted += events_deleted
                        total_findings_deleted += findings_deleted
                        logger.info(
                            "Deleted %s events and %s findings where %s='%s' older than %s days",
                            events_deleted,
                            findings_deleted,
                            split_by,
                            value,
                            retention_days,
                        )
                else:
                    # Bulk delete without splitting
                    queryset = self.get_deletable_queryset(created__lt=threshold)
                    events_deleted, findings_deleted = self.deletion_counts(queryset)
                    total_events_deleted += events_deleted
                    total_findings_deleted += findings_deleted
                    logger.info(
                        "Deleted %s events and %s findings older than %s days (bulk)",
                        events_deleted,
                        findings_deleted,
                        retention_days,
                    )
            
            logger.info(
                "Total deleted: %s events and %s findings older than %s days",
                total_events_deleted,
                total_findings_deleted,
                retention_days,
            )
            # Note: No finding created for retention as it's maintenance
        except Exception as e:
            logger.error(f"Error in {self.name}: {e}")
            # Could send alert on failure, but for now just log
