"""
Django settings for SIEMatic web role.

For web server (Django app).
"""

from .base import *

# Allow configuring hosts via environment for flexibility in different deploys.
# Default to localhost, loopback and the compose service name. Include IPv6 loopback.
ALLOWED_HOSTS = env_list(
    'DJANGO_ALLOWED_HOSTS',
    ['localhost', '127.0.0.1', 'siematic-web', '::1'],
)
