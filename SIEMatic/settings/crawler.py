"""
Django settings for SIEMatic crawler role.

For running the crawlers.
"""

from .base import *

# Email settings for file-based backend
EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
EMAIL_FILE_PATH = BASE_DIR / 'emails'
DEFAULT_FROM_EMAIL = 'siematic@example.com'

CRAWLER_PLUGINS = [
    'crawlers.plugins.failed_login_crawler.FailedLoginCrawler',
    'crawlers.plugins.always_finding_crawler.AlwaysFindingCrawler',
    'crawlers.plugins.data_retention_crawler.DataRetentionCrawler',
]

CRAWLER_CONFIGS = {
    'failed_login_crawler': {
        'name': 'failed_login_crawler',
        'enabled': True,
        'type': 'daemon',  # 'daemon' or 'scheduled'
        'restart': True,   # True (infinite), False (none), or int (max attempts)
        'interval': 60,    # Scan interval in seconds (for daemon)
        'realert_cooldown': 300,  # Seconds to prevent re-alerting same event
        'db_alias': 'default',
        'alerting_plugins': ['email_alert'],  # Alerting plugins to use for this crawler
    },
    'always_finding_crawler': {
        'name': 'always_finding_crawler',
        'enabled': True,
        'type': 'scheduled',  # Run on schedule
        'schedule': '*/1 * * * *',  # Every minute (cron syntax)
        'db_alias': 'default',
        'alerting_plugins': ['email_alert'],  # Send email alerts
        'realert_cooldown': 60 * 5,  #  Cooldown period in seconds (one hour)
    },
    '30_day_retention_crawler': {
        'name': 'data_retention_crawler',
        'enabled': True,
        'type': 'scheduled',
        'schedule': '0,5,10,15,20,25,30,35,40,45,50,55 * * * *',  # Every 5 minutes
        'retention_days': 30,
        'db_alias': 'default',
        'rules': [
            {
                'split_by': 'index',
                'allow': ['default', 'sysmon', 'security'],
                'deny': [],
            },
        ],
    },
    '7_day_retention_crawler': {
        'name': 'data_retention_crawler',
        'enabled': True,
        'type': 'scheduled',
        'schedule': '1,6,11,16,21,26,31,36,41,46,51,56 * * * *',  # Every 5 minutes
        'retention_days': 7,
        'db_alias': 'default',
        'rules': [
            {
                'split_by': 'index',
                'allow': ['windows_events', 'scheduled_tasks'],
                'deny': [],
            },
        ],
    },
    '3_day_retention_crawler': {
        'name': 'data_retention_crawler',
        'enabled': True,
        'type': 'scheduled',
        'schedule': '2,7,12,17,22,27,32,37,42,47,52,57 * * * *',  # Every 5 minutes
        'retention_days': 3,
        'db_alias': 'default',
        'rules': [
            {
                'split_by': 'index',
                'allow': ['watchdog'],
                'deny': [],
            },
        ],
    },
}

ALERTING_PLUGINS = [
    'crawlers.alerting.email_alert.EmailAlert',
]

ALERTING_CONFIGS = {
    'email_alert': {
        'recipients': ['admin@example.com'],  # List of email addresses
        'from_email': 'siematic@example.com',  # Optional, defaults to DEFAULT_FROM_EMAIL
    },
}