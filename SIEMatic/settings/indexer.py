"""
Django settings for SIEMatic indexer role.

For running the indexer.
"""

from .base import *

INDEXER = {
    'host': os.getenv('INDEXER_HOSTNAME', 'localhost'),
    'port': os.getenv('INDEXER_PORT', '8000'),
    'ssl_cert': os.getenv('INDEXER_SSL_CERT') or None,
    'ssl_key': os.getenv('INDEXER_SSL_KEY') or None,
}
ALLOWED_HOSTS = env_list(
    'DJANGO_ALLOWED_HOSTS',
    ['localhost', '127.0.0.1', 'siematic-indexer', '::1'],
)
