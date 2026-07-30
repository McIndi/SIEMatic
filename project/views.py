"""
Views for the project app.

This module contains Django views for the landing page and user profiles.
"""

import logging
from django.contrib import messages
from django.shortcuts import render
from .forms import UserProfileForm
from .models import UserProfile
from django.contrib.auth.decorators import login_required

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
