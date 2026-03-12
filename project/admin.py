"""
Admin configuration for the project app.

This module registers project-related models with the Django admin interface,
including custom user models and permissions.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Permission

from .forms import CustomUserCreationForm
from .models import (
    CustomUser,
    UserProfile,
)

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """
    Admin interface for CustomUser.

    Uses Django's UserAdmin behavior to ensure password hashing and validation
    work correctly when creating users from the admin site.
    """

    add_form = CustomUserCreationForm
    model = CustomUser
    list_display = ("username", "email", "is_staff", "is_superuser", "is_active")
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "email", "password1", "password2"),
            },
        ),
    )


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """
    Admin interface for user profiles.
    """

    list_display = ("user", "theme_preference")

@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    """
    Admin interface for Permission model.

    Provides a list view for permissions with name, codename, and content type.
    """
    list_display = ("name", "codename", "content_type")