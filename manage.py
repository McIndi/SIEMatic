#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
from pathlib import Path
import secrets
import sys


def configure_rundev_environment():
    """Set isolated defaults that let ``rundev`` bootstrap a fresh clone."""
    if len(sys.argv) < 2 or sys.argv[1] != 'rundev':
        return

    project_root = Path(__file__).resolve().parent
    os.environ['DJANGO_SETTINGS_MODULE'] = 'SIEMatic.settings.web'
    os.environ.setdefault('DJANGO_SECRET_KEY', secrets.token_urlsafe(50))
    os.environ['DJANGO_DEBUG'] = 'True'
    os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1,::1'
    os.environ['SIEMATIC_TLS_ENABLED'] = 'True'
    os.environ['DATABASE_ENGINE'] = 'django.db.backends.sqlite3'
    os.environ['DATABASE_NAME'] = str(project_root / 'db.sqlite3')
    for name in (
        'DATABASE_USER',
        'DATABASE_PASSWORD',
        'DATABASE_HOST',
        'DATABASE_PORT',
    ):
        os.environ.pop(name, None)


def main():
    """Run administrative tasks."""
    configure_rundev_environment()
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
