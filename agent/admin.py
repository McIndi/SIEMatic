"""
Admin configuration for agent app.
Provides registration and customization for agent models in Django admin.
"""

from django.contrib import admin

from agent.models import Agent, BatchReceipt, Checkpoint


class CheckpointInline(admin.TabularInline):
    model = Checkpoint
    extra = 0
    readonly_fields = ('target', 'cursor', 'index', 'source', 'events_delivered', 'updated')


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ('agent_id', 'hostname', 'user', 'last_seen', 'events_delivered')
    search_fields = ('agent_id', 'hostname', 'user__username')
    readonly_fields = ('first_seen', 'last_seen', 'last_event_at', 'events_delivered')
    inlines = (CheckpointInline,)


@admin.register(Checkpoint)
class CheckpointAdmin(admin.ModelAdmin):
    list_display = ('target', 'agent', 'index', 'source', 'updated', 'events_delivered')
    search_fields = ('target', 'agent__agent_id', 'index', 'source')
    readonly_fields = ('updated',)


@admin.register(BatchReceipt)
class BatchReceiptAdmin(admin.ModelAdmin):
    list_display = ('target', 'batch_id', 'count', 'created')
    search_fields = ('target', 'batch_id', 'content_digest')
    readonly_fields = ('target', 'batch_id', 'content_digest', 'cursor', 'count', 'created')
