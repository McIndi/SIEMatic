"""
Management command to run crawler plugins as a service.
"""

import logging
import importlib
import multiprocessing
import time
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.conf import settings
import django

logger = logging.getLogger(__name__)

try:
    from croniter import croniter
except ImportError:
    croniter = None
    logger.warning("croniter not installed, scheduled plugins will use simple intervals")

def run_daemon_plugin(plugin_class, config):
    """
    Run a daemon plugin (plugin handles its own loop).
    """
    django.setup()  # Initialize Django in child process
    plugin = plugin_class(config)
    logger.info(f"Starting daemon plugin: {plugin.name}")
    plugin.run()

def run_scheduled_plugin(plugin_class, config):
    """
    Run a scheduled plugin once.
    """
    django.setup()  # Initialize Django in child process
    plugin = plugin_class(config)
    logger.info(f"Running scheduled plugin: {plugin.name}")
    plugin.run()

class Command(BaseCommand):
    help = 'Run crawler plugins as a service with daemon and scheduled modes'

    def add_arguments(self, parser):
        parser.add_argument(
            '--plugin',
            type=str,
            help='Specific plugin to run (for testing, not service mode)',
        )

    def handle(self, *args, **options):
        plugin_name = options.get('plugin')
        if plugin_name:
            # Run specific plugin once for testing
            self.run_single_plugin(plugin_name)
            return

        # Service mode
        crawler_plugins = getattr(settings, 'CRAWLER_PLUGINS', [])
        crawler_configs = getattr(settings, 'CRAWLER_CONFIGS', {})

        # Load plugin classes
        plugins = {}
        for plugin_path in crawler_plugins:
            try:
                module_path, class_name = plugin_path.rsplit('.', 1)
                module = importlib.import_module(module_path)
                plugin_class = getattr(module, class_name)
                name = getattr(plugin_class, 'name', class_name.lower())
                plugins[name] = plugin_class
            except Exception as e:
                logger.error(f"Failed to load plugin {plugin_path}: {e}")

        # Track processes and schedules
        daemon_processes = {}  # name: {'process': proc, 'restart_count': 0}
        scheduled_last_runs = {}
        scheduled_next_runs = {}

        # Initialize schedules
        for name, plugin_class in plugins.items():
            config = crawler_configs.get(name, {})
            plugin_type = config.get('type', 'scheduled')
            if plugin_type == 'scheduled':
                schedule = config.get('schedule')
                if schedule and croniter:
                    cron = croniter(schedule, datetime.now())
                    scheduled_next_runs[name] = cron.get_next(datetime)
                    scheduled_last_runs[name] = None
                else:
                    # Default to every 5 minutes if no cron
                    scheduled_next_runs[name] = datetime.now()
                    scheduled_last_runs[name] = None

        logger.info("Starting crawler service")
        try:
            while True:
                # Start/monitor daemon plugins
                for name, plugin_class in plugins.items():
                    config = crawler_configs.get(name, {})
                    plugin_type = config.get('type', 'scheduled')
                    if plugin_type == 'daemon':
                        restart = config.get('restart', False)
                        max_restarts = float('inf') if restart is True else (restart if isinstance(restart, int) else 0)
                        
                        if name not in daemon_processes:
                            # Start new
                            proc = multiprocessing.Process(target=run_daemon_plugin, args=(plugin_class, config))
                            proc.start()
                            daemon_processes[name] = {'process': proc, 'restart_count': 0}
                            logger.info(f"Started daemon process for {name}")
                        else:
                            proc_info = daemon_processes[name]
                            if not proc_info['process'].is_alive():
                                if proc_info['restart_count'] < max_restarts:
                                    # Restart
                                    proc = multiprocessing.Process(target=run_daemon_plugin, args=(plugin_class, config))
                                    proc.start()
                                    proc_info['process'] = proc
                                    proc_info['restart_count'] += 1
                                    logger.info(f"Restarted daemon process for {name} (attempt {proc_info['restart_count']})")
                                else:
                                    logger.warning(f"Daemon process for {name} died, restart limit reached ({max_restarts})")
                                    del daemon_processes[name]

                # Check scheduled plugins
                now = datetime.now()
                for name, plugin_class in plugins.items():
                    config = crawler_configs.get(name, {})
                    plugin_type = config.get('type', 'scheduled')
                    if plugin_type == 'scheduled':
                        next_run = scheduled_next_runs.get(name)
                        if next_run and now >= next_run:
                            # Spawn process for scheduled run
                            proc = multiprocessing.Process(target=run_scheduled_plugin, args=(plugin_class, config))
                            proc.start()
                            scheduled_last_runs[name] = now
                            # Update next run
                            schedule = config.get('schedule')
                            if schedule and croniter:
                                cron = croniter(schedule, now)
                                scheduled_next_runs[name] = cron.get_next(datetime)
                            else:
                                # Default interval
                                interval = config.get('interval', 300)  # 5 minutes
                                scheduled_next_runs[name] = now + timedelta(seconds=interval)
                            logger.info(f"Scheduled run for {name} at {now}")

                time.sleep(10)  # Check every 10 seconds

        except KeyboardInterrupt:
            logger.info("Stopping crawler service")
            for proc_info in daemon_processes.values():
                proc = proc_info['process']
                if proc.is_alive():
                    proc.terminate()
                    proc.join()
            self.stdout.write("Service stopped")

    def run_single_plugin(self, plugin_name):
        crawler_plugins = getattr(settings, 'CRAWLER_PLUGINS', [])
        crawler_configs = getattr(settings, 'CRAWLER_CONFIGS', {})

        # Load plugin classes
        plugins = {}
        for plugin_path in crawler_plugins:
            try:
                module_path, class_name = plugin_path.rsplit('.', 1)
                module = importlib.import_module(module_path)
                plugin_class = getattr(module, class_name)
                name = getattr(plugin_class, 'name', class_name.lower())
                plugins[name] = plugin_class
            except Exception as e:
                logger.error(f"Failed to load plugin {plugin_path}: {e}")

        if plugin_name not in plugins:
            self.stderr.write(f"Unknown plugin: {plugin_name}")
            return
        plugin_class = plugins[plugin_name]
        config = crawler_configs.get(plugin_name, {})
        plugin = plugin_class(config)
        plugin.run()
        self.stdout.write(f"Ran plugin: {plugin_name}")