"""
Django settings for SIEMatic indexer role.

For running the indexer.
"""

from .base import *

INDEXER = {
    'host': os.getenv('INDEXER_HOSTNAME'),
    'port': os.getenv('INDEXER_PORT'),
}
ALLOWED_HOSTS = os.environ.get(
    'DJANGO_ALLOWED_HOSTS',
    'localhost,127.0.0.1,siematic-indexer,::1'
).split(',')
