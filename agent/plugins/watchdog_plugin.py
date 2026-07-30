"""
WatchdogPlugin: Monitors file system changes and sends events to event_queue.
"""

import time
import logging
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)
logger.debug("agent.plugins.watchdog_plugin module loaded.")
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler

class WatchdogPlugin(PatternMatchingEventHandler):
    """
    Monitor file system changes.
    """
    def __init__(self, config, event_queue, stop_event):
        super(WatchdogPlugin, self).__init__(
            patterns=config.get('patterns', ['*']),
            ignore_patterns=config.get('ignore_patterns', []),
            ignore_directories=config.get('ignore_directories', True),
            case_sensitive=config.get('case_sensitive', False)
        )
        self.event_queue = event_queue
        self.stop_event = stop_event
        configured_path = Path(config.get('path_to_watch', '.')).expanduser()
        if not configured_path.is_absolute():
            configured_path = settings.BASE_DIR / configured_path
        watch_path = configured_path.resolve()
        log_path = (settings.BASE_DIR / 'logs').resolve()
        if (
            watch_path == log_path
            or watch_path in log_path.parents
            or log_path in watch_path.parents
        ):
            message = (
                f"Refusing to watch {watch_path}: recursive monitoring overlaps "
                f"SIEMatic's log directory {log_path}"
            )
            logger.error(message)
            raise ValueError(message)
        if not watch_path.is_dir():
            message = (
                f"path_to_watch '{watch_path}' does not exist. SIEMatic will not "
                "create it automatically; create the directory yourself or fix "
                "the 'path_to_watch' setting for the watchdog plugin."
            )
            logger.error(message)
            raise ValueError(message)
        self.path = str(watch_path)
        self.observer = Observer()
        self.index = config.get('index', 'default')
        self.host = config.get('host', 'localhost')
        self.source = config.get('source', 'watchdog')
        self.sourcetype = config.get('sourcetype', 'json')
        self.db_alias = config.get('db_alias', None)
        logger.info("WatchdogPlugin initialized for path=%s", self.path)

    def run(self):
        logger.info("WatchdogPlugin run started.")
        self.observer.schedule(self, self.path, recursive=True)
        self.observer.start()
        try:
            while not self.stop_event.is_set():
                time.sleep(1)
        except Exception:
            logger.exception("Exception in WatchdogPlugin run")
        finally:
            self.observer.stop()
            self.observer.join()
            logger.info("WatchdogPlugin observer stopped.")

    def on_created(self, event):
        logger.info("File created: %s", event.src_path)
        payload = {
            'src_path': event.src_path,
            'event_type': event.event_type,
            'is_directory': event.is_directory,
            'timestamp': time.time(),
            'index': self.index,
            'host': self.host,
            'source': self.source,
            'sourcetype': self.sourcetype
        }
        if self.db_alias:
            payload['db_alias'] = self.db_alias
        self.event_queue.put(payload)

    def on_modified(self, event):
        logger.info("File modified: %s", event.src_path)
        payload = {
            'src_path': event.src_path,
            'event_type': event.event_type,
            'is_directory': event.is_directory,
            'timestamp': time.time(),
            'index': self.index,
            'host': self.host,
            'source': self.source,
            'sourcetype': self.sourcetype
        }
        if self.db_alias:
            payload['db_alias'] = self.db_alias
        self.event_queue.put(payload)

    def on_deleted(self, event):
        logger.info("File deleted: %s", event.src_path)
        payload = {
            'src_path': event.src_path,
            'event_type': event.event_type,
            'is_directory': event.is_directory,
            'timestamp': time.time(),
            'index': self.index,
            'host': self.host,
            'source': self.source,
            'sourcetype': self.sourcetype
        }
        if self.db_alias:
            payload['db_alias'] = self.db_alias
        self.event_queue.put(payload)

    def on_moved(self, event):
        logger.info("File moved: %s", event.src_path)
        payload = {
            'src_path': event.src_path,
            'dest_path': event.dest_path,
            'event_type': event.event_type,
            'is_directory': event.is_directory,
            'timestamp': time.time(),
            'index': self.index,
            'host': self.host,
            'source': self.source,
            'sourcetype': self.sourcetype
        }
        if self.db_alias:
            payload['db_alias'] = self.db_alias
        self.event_queue.put(payload)
