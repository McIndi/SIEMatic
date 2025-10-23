"""
Management command for running the agent heartbeat and plugin manager.
Handles plugin lifecycle and sends heartbeat via WebSocket.
"""

import time
import asyncio
from django.core.management.base import BaseCommand
import websockets
import json
from django.conf import settings
import signal
import logging

from django.conf import settings
from agent.plugins.plugin_process_manager import PluginProcessManager

logger = logging.getLogger(__name__)
logger.debug("agent.management.commands.agent module loaded.")

class GracefulExit(SystemExit):
    """
    Exception for graceful shutdown on SIGINT.
    """
    pass

def handle_sigint(signum, frame):
    """
    Signal handler for SIGINT to trigger graceful exit.
    """
    logger.critical("SIGINT received, raising GracefulExit.")
    raise GracefulExit()


class Command(BaseCommand):
    """
    Django management command to run the agent heartbeat and manage plugins.
    Sends heartbeat every 10 seconds via WebSocket and manages plugin lifecycle.
    """
    help = 'Agent: sends heartbeat every 10 seconds via WebSocket.'

    def __init__(self):
        super().__init__()
        self.plugin_managers = {}
        logger.debug("Initialized Command with empty plugin_managers.")

    async def send_heartbeat(self):
        """
        Main loop to send heartbeat and manage plugins.
        """
        agent_cfg = getattr(settings, 'AGENT', {})
        logger.info("Loaded AGENT config.")
        plugins = agent_cfg.get('plugins', [])
        for plugin in plugins:
            plugin_name = plugin.get('name')
            logger.debug("Processing plugin: %s with config: %s", plugin_name, plugin)
            if plugin.get('enabled', False):
                # Construct class name from plugin name: e.g., 'windows_event_log' -> 'WindowsEventLogPlugin'
                class_name = ''.join(word.capitalize() for word in plugin_name.split('_')) + 'Plugin'
                module_name = f'agent.plugins.{plugin_name}_plugin'
                plugin_path = plugin.get('path', f'{module_name}:{class_name}')
                logger.info("Enabling plugin '%s' with path '%s'", plugin_name, plugin_path)
                manager = PluginProcessManager(plugin_path, plugin, indexer_cfg=settings.INDEXER, credentials=agent_cfg.get('indexer_credentials'))
                manager.start()
                logger.info("Started PluginProcessManager for '%s'", plugin_name)
                self.plugin_managers[plugin_name] = manager
            else:
                logger.warning("Plugin '%s' is disabled in config.", plugin_name)
        while True:
            try:
                children_alive = {k: m.children_alive() for k, m in self.plugin_managers.items()}
                logger.debug("Children alive status: %s", children_alive)
                for manager in self.plugin_managers.values():
                    manager.check_and_restart()
                    logger.info("Checked and restarted manager: %s", manager)
                    heartbeat = {
                        'type': 'agent_heartbeat',
                        'timestamp': time.time(),
                        'children_alive': children_alive,
                        'plugin_managers': {k: {'alive': m.children_alive(), 'attempts': m.restart_attempts.get(m.plugin_path, 0)} for k, m in self.plugin_managers.items()}
                    }
                    logger.debug("Heartbeat data: %s", heartbeat)
                    # Send credentials with heartbeat if needed
                    manager.event_queue.put(heartbeat)
                    logger.info("Queued heartbeat for manager: %s", manager)
                    self.stdout.write(self.style.SUCCESS(f"Queued heartbeat: {heartbeat}"))
                await asyncio.sleep(10)
                logger.debug("Sleeping for 10 seconds before next heartbeat.")
            except GracefulExit:
                logger.critical("GracefulExit triggered, shutting down agent.")
                self.stdout.write(self.style.WARNING("Shutting down gracefully."))
                for manager in self.plugin_managers.values():
                    manager.stop()
                break
            except Exception as e:
                logger.exception("Heartbeat error occurred: %s", e)
                self.stdout.write(self.style.ERROR(f"Heartbeat error: {e}"))
                await asyncio.sleep(5)
                logger.warning("Sleeping for 5 seconds after error.")

    def handle(self, *args, **options):
        """
        Handle the command execution.
        """
        logger.info("Agent command handle started.")
        signal.signal(signal.SIGINT, handle_sigint)
        try:
            asyncio.run(self.send_heartbeat())
        except GracefulExit:
            logger.critical("Exited on SIGINT.")
            self.stdout.write(self.style.WARNING("Exited on SIGINT."))
