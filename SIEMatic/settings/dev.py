from .base import *

# Development-specific settings
DEBUG = True

# Use the file-based email backend for development
EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
EMAIL_FILE_PATH = BASE_DIR / 'sent_emails'

# Add any other development-specific settings here