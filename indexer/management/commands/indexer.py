"""
Management command for starting the indexer.

This module provides a Django management command to start the Daphne ASGI server
for the indexer component, with process monitoring and graceful shutdown.
"""

import os
from django.core.management.base import BaseCommand, CommandError
import signal
import subprocess
import logging
from pathlib import Path
from twisted.internet.endpoints import quoteStringArgument

logger = logging.getLogger(__name__)


def build_daphne_command(python, host, port, ssl_cert=None, ssl_key=None):
    """Build a Daphne command with either a TCP or verified TLS endpoint."""
    if bool(ssl_cert) != bool(ssl_key):
        raise ValueError(
            'INDEXER_SSL_CERT and INDEXER_SSL_KEY must either both be set or both be unset.'
        )

    command = [python, '-m', 'daphne']
    if ssl_cert:
        cert_path = Path(ssl_cert)
        key_path = Path(ssl_key)
        if not cert_path.is_file():
            raise ValueError(f'INDEXER_SSL_CERT does not exist: {cert_path}')
        if not key_path.is_file():
            raise ValueError(f'INDEXER_SSL_KEY does not exist: {key_path}')
        endpoint = (
            f'ssl:{port}:interface={quoteStringArgument(str(host))}:'
            f'privateKey={quoteStringArgument(str(key_path))}:'
            f'certKey={quoteStringArgument(str(cert_path))}'
        )
        command.extend(['-e', endpoint])
    else:
        command.extend(['-b', host, '-p', str(port)])

    command.extend(['-v', '3', 'SIEMatic.asgi:application'])
    return command


class GracefulExit(SystemExit):
    """
    Exception for graceful exit on signals.
    """
    pass


def handle_sigint(signum, frame):
    """
    Signal handler for SIGINT to raise GracefulExit.
    """
    raise GracefulExit()


class Command(BaseCommand):
    """
    Django management command to start the indexer server.

    Starts Daphne ASGI server and monitors its process, handling shutdown gracefully.
    """
    help = 'Indexer: starts Daphne ASGI server and monitors process.'

    def handle(self, *args, **options):
        """
        Execute the indexer command.

        Starts Daphne server with configured host/port and monitors it.

        Args:
            *args: Positional arguments.
            **options: Keyword options.
        """
        from django.conf import settings
        import time
        import sys

        host = getattr(settings, 'INDEXER', {}).get('host', 'localhost')
        port = str(getattr(settings, 'INDEXER', {}).get('port', 8000))
        indexer_config = getattr(settings, 'INDEXER', {})
        ssl_cert = indexer_config.get('ssl_cert')
        ssl_key = indexer_config.get('ssl_key')
        try:
            daphne_cmd = build_daphne_command(
                sys.executable, host, port, ssl_cert, ssl_key
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        scheme = 'https/wss' if ssl_cert else 'http/ws'
        self.stdout.write(self.style.SUCCESS(
            f"Starting Daphne ASGI server on {scheme}://{host}:{port}..."
        ))
        logger.info("Starting Daphne ASGI server on %s://%s:%s...", scheme, host, port)
        env = os.environ.copy()
        env['INDEXER_MODE'] = '1'  # Mark as indexer mode so web ui isn't hosted by the indexer
        proc = subprocess.Popen(daphne_cmd, env=env)

        def handle_sigint(signum, frame):
            self.stdout.write(self.style.WARNING("SIGINT received, shutting down Daphne..."))
            logger.warning("SIGINT received, shutting down Daphne...")
            proc.terminate()
            raise GracefulExit()

        signal.signal(signal.SIGINT, handle_sigint)
        try:
            while True:
                logger.debug("Daphne is running...")
                retcode = proc.poll()
                if retcode is not None:
                    self.stdout.write(self.style.WARNING(f"Daphne exited with code {retcode}"))
                    logger.warning(f"Daphne exited with code {retcode}")
                    break
                time.sleep(1)
        except GracefulExit:
            self.stdout.write(self.style.WARNING("Exited on SIGINT."))

