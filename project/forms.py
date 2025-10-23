"""
Forms for the project app.

This module defines Django forms for user profiles and custom user creation.
"""
from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import UserProfile, CustomUser

class UserProfileForm(forms.ModelForm):
    """
    Form for editing user profiles.

    Allows updating bio and theme preferences.
    """

    class Meta:
        model = UserProfile
        fields = ['bio', 'theme_preference']


class CustomUserCreationForm(UserCreationForm):
    """
    Form for creating custom users.

    Extends UserCreationForm with username and email fields.
    """

    class Meta:
        model = CustomUser
        fields = ("username", "email")