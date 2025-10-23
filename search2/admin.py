"""
Admin configuration for the search2 app.

This module registers SavedSearch model with the Django admin interface.
"""
from django.contrib import admin
from .models import SavedSearch

@admin.register(SavedSearch)
class SavedSearchAdmin(admin.ModelAdmin):
    """
    Admin interface for SavedSearch model.

    Provides list display and search for saved searches.
    """
    list_display = ("id", "owner", "name", "created_at", "updated_at")
    search_fields = ("name", "owner__username")
