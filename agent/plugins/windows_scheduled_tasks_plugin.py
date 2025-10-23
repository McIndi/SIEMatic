# agent/plugins/windows_scheduled_tasks_plugin.py
import time, json, subprocess, logging, platform
logger = logging.getLogger(__name__)

class WindowsScheduledTasksPlugin:
    """
    Enumerate Scheduled Tasks and emit a snapshot + diffs.
    Config: poll_interval (sec, default 60).
    """
    def __init__(self, config, event_queue, stop_event):
        if platform.system() != 'Windows':
            raise RuntimeError('WindowsScheduledTasksPlugin only runs on Windows')
        self.event_queue = event_queue
        self.stop_event = stop_event
        self.poll_interval = float(config.get('poll_interval', 60))
        self.index  = config.get('index', 'default')
        self.host   = config.get('host', 'localhost')
        self.source = config.get('source', 'scheduled_tasks')
        self.sourcetype = config.get('sourcetype', 'json')
        self.db_alias = config.get('db_alias')

        self._last = {}

    def _list_tasks(self):
        # schtasks /Query /FO JSON requires newer builds; fall back to CSV if needed
        try:
            out = subprocess.check_output(['schtasks', '/Query', '/V', '/FO', 'LIST'], text=True, errors='replace')
        except Exception as e:
            logger.exception("schtasks failed: %s", e); return {}
        tasks, cur = {}, {}
        for line in out.splitlines():
            if not line.strip():
                if cur.get('TaskName'):
                    tasks[cur['TaskName']] = cur; cur = {}
                continue
            if ':' in line:
                k, v = line.split(':', 1)
                cur[k.strip()] = v.strip()
        if cur.get('TaskName'):
            tasks[cur['TaskName']] = cur
        return tasks

    def run(self):
        while not self.stop_event.is_set():
            now = time.time()
            tasks = self._list_tasks()
            # Diff
            added = {k:v for k,v in tasks.items() if k not in self._last}
            removed = {k:v for k,v in self._last.items() if k not in tasks}
            changed = {k:v for k,v in tasks.items() if k in self._last and v != self._last[k]}
            for kind, payload in (('added', added), ('removed', removed), ('changed', changed)):
                if not payload: continue
                event = {
                    'type': 'windows_scheduled_tasks',
                    'event_type': kind,
                    'timestamp': now,
                    'items': payload,
                    'index': self.index,
                    'host': self.host,
                    'source': self.source,
                    'sourcetype': self.sourcetype,
                }
                if self.db_alias:
                    event['db_alias'] = self.db_alias
                self.event_queue.put(event)
            self._last = tasks
            time.sleep(self.poll_interval)