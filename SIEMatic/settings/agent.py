"""
Django settings for SIEMatic agent role.

For running agents.
"""

import os
import socket
import platform

from .base import *

# Agent/Indexer host/port config

# Indexer credentials from environment variables
INDEXER_CREDENTIALS = {
    'username': os.getenv('INDEXER_USERNAME'),
    'password': os.getenv('INDEXER_PASSWORD'),
}

AGENT = {
    'plugins': [
        {
            'name': 'watchdog',
            'enabled': True,
            'patterns': ['logs/*.log'],
            'ignore_patterns': ['*.gz', '*.zip'],
            'ignore_directories': True,
            'case_sensitive': False,
            'db_alias': 'default',
            'index': 'watchdog',
            'host': socket.gethostname(),
            'source': 'watchdog',
            'sourcetype': 'json',
        },
        {
            'name': 'sysmon',
            'enabled': True,
            'poll_interval': 5.0,
            'db_alias': 'default',
            'index': 'sysmon',
            'host': socket.gethostname(),
            'source': 'sysmon',
            'sourcetype': 'json',
        },
        {
            'name': 'tail',
            'enabled': False,
            'patterns': ['logs/*.log'],
            'restart': 5,
            'poll_interval': 1.0,
            'db_alias': 'default',
            'index': 'tail',
            'host': socket.gethostname(),
            'source': 'tail',
            'sourcetype': 'text',
        },
    ],
    'indexer_credentials': INDEXER_CREDENTIALS,
}

INDEXER = {
    'host': os.getenv('INDEXER_HOSTNAME', 'localhost'),
    'port': os.getenv('INDEXER_PORT', '8000'),
    'tls': INDEXER_TLS,
    'ca_bundle': INDEXER_CA_BUNDLE,
}

# Add Windows Event Log plugin if on Windows
if platform.system() == 'Windows':
    AGENT['plugins'].extend(
        [
            {
                'name': 'windows_event_log',
                'enabled': True,
                'log_type': 'System',
                'level': 'ERROR',
                'poll_interval': 10.0,
                'db_alias': 'default',
                'index': 'windows_events',
                'host': socket.gethostname(),
                'source': 'windows_event_log',
                'sourcetype': 'json',
            },
            {
                'name': 'windows_scheduled_tasks',
                'enabled': True,
                'poll_interval': 60,
                'db_alias': 'default',
                'index': 'scheduled_tasks',
                'host': socket.gethostname(),
                'source': 'windows_scheduled_tasks',
                'sourcetype': 'json',
            },
        ]
    )
