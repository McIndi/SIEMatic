from django.contrib import admin
from .models import Finding

@admin.register(Finding)
class FindingAdmin(admin.ModelAdmin):
    list_display = ('rule_name', 'severity', 'status', 'assignee', 'event', 'created_at')
    list_filter = ('severity', 'status', 'assignee', 'rule_name', 'created_at')
    search_fields = ('rule_name', 'description')
