"""
Management command for starting the indexer.

This module provides a Django management command to start the Daphne ASGI server
for the indexer component, with process monitoring and graceful shutdown.
"""

import asyncio
import json
import os
from django.core.management.base import BaseCommand
from channels.layers import get_channel_layer
from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
import websockets
from django.conf import settings
import signal
import subprocess
import logging

logger = logging.getLogger(__name__)


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
        daphne_cmd = [sys.executable, '-m', 'daphne', '-b', host, '-p', port, '-v', '3', 'SIEMatic.asgi:application']

        self.stdout.write(self.style.SUCCESS(f"Starting Daphne ASGI server on {host}:{port}..."))
        logger.info(f"Starting Daphne ASGI server on {host}:{port}...")
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

