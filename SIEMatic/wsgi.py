"""
WSGI config for SIEMatic project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

# Set default settings module if not already set
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SIEMatic.settings.web')

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
