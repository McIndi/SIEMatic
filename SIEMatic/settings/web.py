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

# HTTPS / security headers.
# Set HTTPS_ENABLED=True in production when the app is served over TLS (directly
# or behind a TLS-terminating proxy). Defaults to False so local dev is unaffected.
_https = os.environ.get('HTTPS_ENABLED', 'False').lower() in ('true', '1', 'yes')

SECURE_SSL_REDIRECT = _https
SESSION_COOKIE_SECURE = _https
CSRF_COOKIE_SECURE = _https
SECURE_HSTS_SECONDS = 31536000 if _https else 0  # 1 year when HTTPS is enabled
SECURE_HSTS_INCLUDE_SUBDOMAINS = _https
SECURE_HSTS_PRELOAD = _https

# Safe to enable unconditionally — no HTTPS dependency.
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
