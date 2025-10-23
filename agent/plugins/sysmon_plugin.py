"""
SysmonPlugin: Collects and reports system metrics at intervals.
"""

import time
import psutil
import logging
logger = logging.getLogger(__name__)
logger.debug("agent.plugins.sysmon_plugin module loaded.")

class SysmonPlugin:
    """
    Collects system metrics at a configurable interval and sends them to event_queue.
    Config keys:
      - poll_interval: seconds between checks (default: 5.0)
    """
    def __init__(self, config, event_queue, stop_event):
        self.poll_interval = float(config.get('poll_interval', 5.0))
        self.event_queue = event_queue
        self.stop_event = stop_event
        self.index = config.get('index', 'default')
        self.host = config.get('host', 'localhost')
        self.source = config.get('source', 'system_metrics')
        self.sourcetype = config.get('sourcetype', 'metrics')
        self.db_alias = config.get('db_alias', None)

        logger.info("SysmonPlugin initialized with poll_interval=%s", self.poll_interval)

    def run(self):
        logger.info("SysmonPlugin run started.")
        while not self.stop_event.is_set():
            metrics = {
                'cpu_percent': psutil.cpu_percent(interval=None),
                'cpu_count': psutil.cpu_count(),
                'memory': psutil.virtual_memory()._asdict(),
                'swap': psutil.swap_memory()._asdict(),
                'disk': {p.device: psutil.disk_usage(p.mountpoint)._asdict() for p in psutil.disk_partitions()},
                'net_io': psutil.net_io_counters()._asdict(),
                'boot_time': psutil.boot_time(),
                'timestamp': time.time()
            }
            logger.debug("SysmonPlugin collected metrics: %s", metrics)
            event = {
                'event_type': 'sysmon',
                'metrics': metrics,
                'timestamp': metrics['timestamp'],
                'index': self.index,
                'host': self.host,
                'source': self.source,
                'sourcetype': self.sourcetype
            }
            if self.db_alias:
                event['db_alias'] = self.db_alias
            self.event_queue.put(event)
            time.sleep(self.poll_interval)
