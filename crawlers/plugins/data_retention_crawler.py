"""
Crawler plugin for data retention: Deletes events older than a specified age.
"""

import logging
from datetime import timedelta
from django.utils import timezone
from .base import BaseCrawlerPlugin

logger = logging.getLogger(__name__)

class DataRetentionCrawler(BaseCrawlerPlugin):
    """
    Crawler that enforces data retention policies by deleting old events.
    """
    name = 'data_retention_crawler'

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
            
            total_deleted = 0
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
                        deleted_count, _ = self.get_queryset().filter(**filter_kwargs).delete()
                        total_deleted += deleted_count
                        logger.info(f"Deleted {deleted_count} events where {split_by}='{value}' older than {retention_days} days")
                else:
                    # Bulk delete without splitting
                    queryset = self.get_queryset().filter(created__lt=threshold)
                    deleted_count, _ = queryset.delete()
                    total_deleted += deleted_count
                    logger.info(f"Deleted {deleted_count} events older than {retention_days} days (bulk)")
            
            logger.info(f"Total deleted: {total_deleted} events older than {retention_days} days")
            # Note: No finding created for retention as it's maintenance
        except Exception as e:
            logger.error(f"Error in {self.name}: {e}")
            # Could send alert on failure, but for now just log