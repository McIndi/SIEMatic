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
]

CRAWLER_CONFIGS = {
    'failed_login_crawler': {
        'enabled': True,
        'type': 'daemon',  # 'daemon' or 'scheduled'
        'restart': True,   # True (infinite), False (none), or int (max attempts)
        'interval': 60,    # Scan interval in seconds (for daemon)
        'realert_cooldown': 300,  # Seconds to prevent re-alerting same event
        'db_alias': 'default',
        'alerting_plugins': ['email_alert'],  # Alerting plugins to use for this crawler
    },
    'always_finding_crawler': {
        'enabled': True,
        'type': 'scheduled',  # Run on schedule
        'schedule': '*/1 * * * *',  # Every minute (cron syntax)
        'db_alias': 'default',
        'alerting_plugins': ['email_alert'],  # Send email alerts
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