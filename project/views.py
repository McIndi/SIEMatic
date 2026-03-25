"""
Views for the project app.

This module contains Django views for landing page, user profiles, and registration.
"""

import logging
from django.contrib import messages
from django.shortcuts import render, redirect
from .forms import UserProfileForm
from .models import UserProfile
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from .forms import CustomUserCreationForm

logger = logging.getLogger(__name__)


def landing_page(request):
    """
    Render the landing page.

    Args:
        request: The HTTP request.

    Returns:
        Rendered landing page template.
    """
    logger.debug("Rendering landing page")
    return render(request, 'landing_page.html')


@login_required
def profile_view(request):
    """
    Handle user profile view and updates.

    Args:
        request: The HTTP request.

    Returns:
        Rendered profile page with form.
    """
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    if created:
        logger.info(f"Created new profile for user {request.user.username}")
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully.')
            logger.info(f"Profile updated for user {request.user.username}")
            return render(request, 'profile.html', {'form': form})
    else:
        form = UserProfileForm(instance=profile)
    return render(request, 'profile.html', {'form': form})


def register(request):
    """
    Handle user registration.

    Args:
        request: The HTTP request.

    Returns:
        Rendered registration page with form.
    """
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            logger.info(f"New user registered: {user.username}")
            return redirect('login')
    else:
        form = CustomUserCreationForm()
    return render(request, 'register.html', {'form': form})

@login_required
@require_POST
def toggle_theme(request):
    """Toggle the user's theme preference between light and dark."""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    profile.theme_preference = 'dark' if profile.theme_preference == 'light' else 'light'
    profile.save(update_fields=['theme_preference'])
    return redirect(request.META.get('HTTP_REFERER', '/'))
