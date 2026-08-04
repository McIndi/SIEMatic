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
            'enabled': False,
            'path_to_watch': str(BASE_DIR / 'watched'),
            'patterns': ['*.log'],
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
            'name': 'network_security',
            'enabled': True,
            'poll_interval': 30.0,
            'status_interval': 300.0,
            'include_cmdline': False,
            'db_alias': 'default',
            'index': 'network_security',
            'host': socket.gethostname(),
            'source': 'network_security',
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

# ``rundev`` deliberately collects only lightweight, cross-platform core
# telemetry. The old sysmon-only variable remains as a compatibility alias.
core_only = env_bool(
    'SIEMATIC_AGENT_CORE_ONLY',
    env_bool('SIEMATIC_AGENT_SYSMON_ONLY', False),
)
if core_only:
    AGENT['plugins'] = [
        plugin
        for plugin in AGENT['plugins']
        if plugin['name'] in {'sysmon', 'network_security'}
    ]
