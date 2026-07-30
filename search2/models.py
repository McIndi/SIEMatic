from django.conf import settings
from django.db import models
from django.db.models import Q


class SavedSearchQuerySet(models.QuerySet):
    def visible_to(self, user):
        public_filter = Q(is_public=True)
        if not user or not getattr(user, "is_authenticated", False):
            return self.filter(public_filter)
        return self.filter(
            Q(owner=user) | Q(shared_with=user) | public_filter
        ).distinct()


class SavedSearch(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_searches")
    name = models.CharField(max_length=255)
    query = models.TextField()
    shared_with = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="shared_searches",
    )
    is_public = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = SavedSearchQuerySet.as_manager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
