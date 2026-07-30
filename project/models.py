"""
Models for the project app.

This module defines custom user models and user profiles for the application.
"""
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings

class CustomUser(AbstractUser):
    """
    Custom user model extending Django's AbstractUser.

    Currently uses default fields, but allows for future extensions.
    """


class UserProfile(models.Model):
    """
    User profile model for additional user information.

    Stores bio and theme preferences for users.
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    bio = models.TextField(blank=True, null=True)

    THEME_CHOICES = [
        ("light", "Light"),
        ("dark", "Dark"),
    ]
    theme_preference = models.CharField(
        max_length=10,
        choices=THEME_CHOICES,
        default="light",
        help_text="User's preferred theme mode (light or dark)"
    )

    def __str__(self):
        """
        String representation of the user profile.

        Returns the associated username.
        """
        return self.user.username

