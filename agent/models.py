"""
Models for the agent app.
Define database schema for agent-related data.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class Agent(models.Model):
    agent_id = models.CharField(max_length=255, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name='siematic_agents',
    )
    hostname = models.CharField(max_length=255, blank=True)
    address = models.GenericIPAddressField(blank=True, null=True)
    version = models.CharField(max_length=64, blank=True)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(default=timezone.now, db_index=True)
    last_event_at = models.DateTimeField(blank=True, null=True)
    events_delivered = models.PositiveBigIntegerField(default=0)

    def __str__(self):
        return self.agent_id


class Checkpoint(models.Model):
    target = models.CharField(max_length=512, unique=True)
    cursor = models.TextField()
    agent = models.ForeignKey(
        Agent,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name='checkpoints',
    )
    index = models.CharField(max_length=255)
    source = models.CharField(max_length=512)
    events_delivered = models.PositiveBigIntegerField(default=0)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.target


class BatchReceipt(models.Model):
    target = models.CharField(max_length=512)
    batch_id = models.CharField(max_length=255)
    content_digest = models.CharField(max_length=64)
    cursor = models.TextField()
    count = models.PositiveIntegerField()
    created = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('target', 'batch_id'),
                name='agent_receipt_target_batch_uniq',
            ),
        ]

    def __str__(self):
        return f'{self.target}:{self.batch_id}'
