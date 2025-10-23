"""
Script to create sample event data in the database for development/testing.
"""

import os
import django
import logging
logger = logging.getLogger(__name__)
logger.debug("create_sample_data.py loaded.")

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SIEMatic.settings.dev')
django.setup()

from events.models import Event
from datetime import datetime, timezone
import json

# Create some sample events
logger.info("Preparing sample events data.")
events_data = [
    {
        'host': 'web-server-01',
        'index': 'security',
        'source': '/var/log/auth.log',
        'sourcetype': 'auth_log',
        'data': 'user=alice source_ip=192.168.1.10 event_type=login port=22 timestamp=2023-09-01T10:30:00Z',
        'extracted_fields': {'user': 'alice', 'source_ip': '192.168.1.10', 'event_type': 'login', 'port': 22, 'severity': 'INFO'}
    },
    {
        'host': 'web-server-02',
        'index': 'security',
        'source': '/var/log/auth.log',
        'sourcetype': 'auth_log',
        'data': 'user=bob source_ip=192.168.1.11 event_type=login port=22 timestamp=2023-09-01T11:15:00Z',
        'extracted_fields': {'user': 'bob', 'source_ip': '192.168.1.11', 'event_type': 'login', 'port': 22, 'severity': 'INFO'}
    },
    {
        'host': 'web-server-01',
        'index': 'security',
        'source': '/var/log/auth.log',
        'sourcetype': 'auth_log',
        'data': 'user=admin source_ip=10.0.0.100 event_type=failed_login port=22 timestamp=2023-09-01T12:00:00Z',
        'extracted_fields': {'user': 'admin', 'source_ip': '10.0.0.100', 'event_type': 'failed_login', 'port': 22, 'severity': 'WARNING'}
    },
    {
        'host': 'file-server-01',
        'index': 'access',
        'source': '/var/log/apache/access.log',
        'sourcetype': 'apache_access',
        'data': 'user=alice source_ip=192.168.1.10 event_type=file_access port=80 timestamp=2023-09-01T13:45:00Z',
        'extracted_fields': {'user': 'alice', 'source_ip': '192.168.1.10', 'event_type': 'file_access', 'port': 80, 'severity': 'INFO'}
    },
    {
        'host': 'db-server-01',
        'index': 'security',
        'source': '/var/log/auth.log',
        'sourcetype': 'auth_log',
        'data': 'user=charlie source_ip=192.168.1.12 event_type=login port=443 timestamp=2023-09-01T14:20:00Z',
        'extracted_fields': {'user': 'charlie', 'source_ip': '192.168.1.12', 'event_type': 'login', 'port': 443, 'severity': 'INFO'}
    },
    {
        'host': 'web-server-01',
        'index': 'security',
        'source': '/var/log/auth.log',
        'sourcetype': 'auth_log',
        'data': 'user=admin source_ip=10.0.0.100 event_type=failed_login port=22 timestamp=2023-09-01T15:30:00Z',
        'extracted_fields': {'user': 'admin', 'source_ip': '10.0.0.100', 'event_type': 'failed_login', 'port': 22, 'severity': 'CRITICAL'}
    },
]

created_count = 0
for event_dict in events_data:
    try:
        event = Event.objects.create(
            host=event_dict['host'],
            index=event_dict['index'],
            source=event_dict['source'],
            sourcetype=event_dict['sourcetype'],
            data=event_dict['data'],
            extracted_fields=event_dict['extracted_fields'],
            timestamp=datetime.now(timezone.utc)
        )
        logger.info("Created event for host=%s, index=%s", event.host, event.index)
        created_count += 1
    except Exception as e:
        logger.error("Failed to create event for host=%s: %s", event_dict.get('host'), e)

logger.info("Finished creating %d sample events.", created_count)

print(f'Created/verified {Event.objects.count()} events in database')
print('Sample event data:')
for event in Event.objects.all()[:3]:
    print(f'  {event.host} - {event.index} - {event.sourcetype} - {event.data[:50]}...')