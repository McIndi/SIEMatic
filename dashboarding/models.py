from django.db import models
from django.conf import settings

class Dashboard(models.Model):
    """
    Model representing a dashboard.

    A dashboard is a collection of panels with a name and optional populating search.
    """
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    defaults = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

class Panel(models.Model):
    """
    Model representing a dashboard panel.

    A panel contains a search query and visualization settings for displaying
    data in charts or tables within a dashboard.
    """
    dashboard = models.ForeignKey(Dashboard, related_name='panels', on_delete=models.CASCADE)
    search = models.TextField(blank=True, null=True, help_text="Enter a SavedSearch name or raw search text.")
    VISUALIZATION_TYPE_CHOICES = [
        ("table", "Table"),
        ("chart", "Chart"),
    ]
    visualization_type = models.CharField(max_length=16, choices=VISUALIZATION_TYPE_CHOICES, default="table")
    # Chart-specific fields
    chart_type = models.CharField(max_length=32, blank=True, null=True)  # e.g., bar, line, pie
    x_field = models.CharField(max_length=128, blank=True, null=True)
    y_field = models.CharField(max_length=128, blank=True, null=True)
    by_field = models.CharField(max_length=128, blank=True, null=True)
    title = models.CharField(max_length=255, blank=True, null=True)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title or f"Panel {self.pk}"
