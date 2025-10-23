"""
Django settings for SIEMatic indexer role.

For running the indexer.
"""

from .base import *

INDEXER = {
    'host': 'localhost',
    'port': 5001,
}