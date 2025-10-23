# agent/plugins/linux_schedulers_plugin.py
import os, subprocess, time, logging, platform, json
logger = logging.getLogger(__name__)

class LinuxSchedulersPlugin:
    """
    Emit diffs for cron and systemd timers/services.
    Config: poll_interval (default 60).
    """
    def __init__(self, config, event_queue, stop_event):
        if platform.system() != 'Linux':
            raise RuntimeError('LinuxSchedulersPlugin only runs on Linux')
        self.event_queue = event_queue
        self.stop_event = stop_event
        self.poll_interval = float(config.get('poll_interval', 60))
        self.index=config.get('index','default'); self.host=config.get('host','localhost')
        self.source=config.get('source','linux_schedulers'); self.sourcetype=config.get('sourcetype','json')
        self.db_alias = config.get('db_alias')
        self._last = {'cron':{}, 'systemd':{}}

    def _cron_state(self):
        items = {}
        # system crontab + cron.d
        for path in ['/etc/crontab'] + [os.path.join('/etc/cron.d', f) for f in os.listdir('/etc/cron.d') if os.path.isfile(os.path.join('/etc/cron.d', f))]:
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    items[path] = f.read()
            except Exception: pass
        # per-user crontab
        for udir in ['/var/spool/cron', '/var/spool/cron/crontabs']:
            if os.path.isdir(udir):
                for name in os.listdir(udir):
                    p = os.path.join(udir, name)
                    try:
                        with open(p, 'r', encoding='utf-8', errors='replace') as f:
                            items[f'user:{name}'] = f.read()
                    except Exception: pass
        return items

    def _systemd_state(self):
        def run(cmd): 
            try: return subprocess.check_output(cmd, text=True, errors='replace')
            except Exception: return ''
        timers = run(['systemctl','list-timers','--all','--no-pager','--no-legend'])
        services = run(['systemctl','list-unit-files','--type=service','--no-pager','--no-legend'])
        return {'timers': timers, 'services': services}

    def run(self):
        while not self.stop_event.is_set():
            now = time.time()
            cron = self._cron_state()
            sysd = self._systemd_state()
            cur = {'cron': cron, 'systemd': sysd}
            for key in ['cron','systemd']:
                prev = self._last.get(key,{})
                if cur[key] != prev:
                    event = {'type':'linux_schedulers','event_scope':key,'event_type':'changed',
                             'timestamp':now,'current':cur[key],'previous':prev,
                             'index':self.index,'host':self.host,'source':self.source,'sourcetype':self.sourcetype}
                    if self.db_alias: event['db_alias']=self.db_alias
                    self.event_queue.put(event)
            self._last = cur
            time.sleep(self.poll_interval)