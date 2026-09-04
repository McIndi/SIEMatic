"""
Views for the project app.

This module contains Django views for the landing page and user profiles.
"""

import logging
from django.contrib import messages
from django.db import connections
from django.db.utils import OperationalError
from django.http import HttpResponse
from django.shortcuts import render
from .forms import UserProfileForm
from .models import UserProfile
from django.contrib.auth.decorators import login_required

logger = logging.getLogger(__name__)


def healthz(request):
    """
    Report that the process is running.

    A liveness probe. It touches nothing else, so a slow database or a broken
    auth backend cannot get the container restarted.

    Args:
        request: The HTTP request.

    Returns:
        A 200 response.
    """
    return HttpResponse('ok', content_type='text/plain')


def readyz(request):
    """
    Report whether the process can serve traffic.

    A readiness probe. It runs one trivial query, so a pod is pulled out of the
    service while its database connection is down.

    Args:
        request: The HTTP request.

    Returns:
        A 200 response, or 503 when the database is unreachable.
    """
    try:
        with connections['default'].cursor() as cursor:
            cursor.execute('SELECT 1')
    except OperationalError as error:
        logger.warning(f'Readiness probe failed: {error}')
        return HttpResponse('database unavailable', status=503, content_type='text/plain')
    return HttpResponse('ok', content_type='text/plain')


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
