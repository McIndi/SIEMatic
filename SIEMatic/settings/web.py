"""
Django settings for SIEMatic web role.

For web server (Django app).
"""

from .base import *
import os

# Allow configuring hosts via environment for flexibility in different deploys.
# Default to localhost, loopback and the compose service name. Include IPv6 loopback.
ALLOWED_HOSTS = os.environ.get(
    'DJANGO_ALLOWED_HOSTS',
    'localhost,127.0.0.1,siematic-web,::1'
).split(',')
