"""
WindowsEventLogPlugin: Monitors Windows Event Log and sends new events to event_queue based on level.
"""

import time
import logging
import platform
import os
import json

logger = logging.getLogger(__name__)
logger.debug("agent.plugins.windows_event_log_plugin module loaded.")

# Only import on Windows
if platform.system() == 'Windows':
    import win32evtlog
    import win32con
    import win32evtlogutil
    import pywintypes
else:
    win32evtlog = None

class WindowsEventLogPlugin:
    """
    Monitors Windows Event Log for new events above a configurable level. Sends events to event_queue.
    Config keys:
      - log_type: Event log type (e.g., 'System', 'Application', 'Security') (default: 'System')
      - level: Minimum level to index ('ERROR', 'WARNING', 'INFORMATION', 'AUDIT_SUCCESS', 'AUDIT_FAILURE') (default: 'ERROR')
      - poll_interval: seconds between checks (default: 10.0)
    """
    LEVEL_MAPPING = {
        'ERROR': win32con.EVENTLOG_ERROR_TYPE if win32evtlog else 1,
        'WARNING': win32con.EVENTLOG_WARNING_TYPE if win32evtlog else 2,
        'INFORMATION': win32con.EVENTLOG_INFORMATION_TYPE if win32evtlog else 4,
        'AUDIT_SUCCESS': win32con.EVENTLOG_AUDIT_SUCCESS if win32evtlog else 8,
        'AUDIT_FAILURE': win32con.EVENTLOG_AUDIT_FAILURE if win32evtlog else 16,
    }

    def __init__(self, config, event_queue, stop_event):
        if platform.system() != 'Windows':
            raise RuntimeError("WindowsEventLogPlugin only works on Windows")
        self.log_type = config.get('log_type', 'System')
        self.level_str = config.get('level', 'ERROR').upper()
        self.min_level = self.LEVEL_MAPPING.get(self.level_str, self.LEVEL_MAPPING['ERROR'])
        self.poll_interval = float(config.get('poll_interval', 10.0))
        self.event_queue = event_queue
        self.stop_event = stop_event
        self.state_dir = os.path.expanduser('~/.siematic/state')
        os.makedirs(self.state_dir, exist_ok=True)
        self.state_file = os.path.join(self.state_dir, f'{self.log_type}.json')
        self.last_record = self._load_last_record()
        self.index = config.get('index', 'default')
        self.host = config.get('host', 'localhost')
        self.source = config.get('source', 'windows_event_log')
        self.sourcetype = config.get('sourcetype', 'json')
        self.db_alias = config.get('db_alias', None)
        logger.info("WindowsEventLogPlugin initialized with log_type=%s, level=%s, poll_interval=%s", self.log_type, self.level_str, self.poll_interval)

    def run(self):
        logger.info("WindowsEventLogPlugin run started.")
        while not self.stop_event.is_set():
            try:
                self._read_new_events()
            except Exception as e:
                logger.exception("Error reading Windows Event Log: %s", e)
            time.sleep(self.poll_interval)

    def _read_new_events(self):
        # Open the event log
        hand = win32evtlog.OpenEventLog(None, self.log_type)
        try:
            # Get total records
            total = win32evtlog.GetNumberOfEventLogRecords(hand)
            if total == 0:
                return
            # Read forwards sequentially from the beginning, filter by record number
            flags = win32evtlog.EVENTLOG_FORWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
            events = win32evtlog.ReadEventLog(hand, flags, 0)
            for event in events:
                if event.RecordNumber > self.last_record and event.EventType >= self.min_level:
                    event_data = {
                        'record_number': event.RecordNumber,
                        'event_id': event.EventID,
                        'source_name': event.SourceName,
                        'time_generated': event.TimeGenerated.Format(),
                        'event_type': event.EventType,
                        'category': event.EventCategory,
                        'strings': event.StringInserts,
                        'data': event.Data if event.Data else None,
                        'computer_name': event.ComputerName,
                        'sid': str(event.Sid) if event.Sid else None,
                    }
                    queue_event = {
                        'src_log': self.log_type,
                        'event_type': 'windows_event',
                        'event_data': event_data,
                        'timestamp': time.time(),
                        'index': self.index,
                        'host': self.host,
                        'source': self.source,
                        'sourcetype': self.sourcetype,
                    }
                    if self.db_alias:
                        queue_event['db_alias'] = self.db_alias
                    self.event_queue.put(queue_event)
                    logger.debug("Queued Windows event: %s", event.RecordNumber)
                self.last_record = max(self.last_record, event.RecordNumber)
            self._save_last_record()
        finally:
            win32evtlog.CloseEventLog(hand)

    def _load_last_record(self):
        try:
            with open(self.state_file, 'r') as f:
                data = json.load(f)
                return data.get('last_record', 0)
        except (FileNotFoundError, json.JSONDecodeError):
            return 0

    def _save_last_record(self):
        try:
            with open(self.state_file, 'w') as f:
                json.dump({'last_record': self.last_record}, f)
        except Exception as e:
            logger.warning("Failed to save last_record: %s", e)