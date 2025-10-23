"""
Admin configuration for the project app.

This module registers project-related models with the Django admin interface,
including custom user models and permissions.
"""

from django.contrib import admin
from django.contrib.auth.models import Permission

from .models import (
    CustomUser,
    UserProfile,
)

admin.site.register(CustomUser)
admin.site.register(UserProfile)

@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    """
    Admin interface for Permission model.

    Provides a list view for permissions with name, codename, and content type.
    """
    list_display = ("name", "codename", "content_type")