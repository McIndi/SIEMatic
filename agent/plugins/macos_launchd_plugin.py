# agent/plugins/macos_launchd_plugin.py
import os, plistlib, time, logging, platform, glob, hashlib
logger = logging.getLogger(__name__)

class MacOSLaunchdPlugin:
    """
    Track LaunchAgents/LaunchDaemons; emit adds/removes/changes.
    Config: poll_interval (default 60).
    """
    PATHS = [
        '/Library/LaunchAgents', '/Library/LaunchDaemons',
        os.path.expanduser('~/Library/LaunchAgents')
    ]

    def __init__(self, config, event_queue, stop_event):
        if platform.system() != 'Darwin':
            raise RuntimeError('MacOSLaunchdPlugin only runs on macOS')
        self.event_queue = event_queue
        self.stop_event = stop_event
        self.poll_interval = float(config.get('poll_interval', 60))
        self.index=config.get('index','default'); self.host=config.get('host','localhost')
        self.source=config.get('source','macos_launchd'); self.sourcetype=config.get('sourcetype','json')
        self.db_alias=config.get('db_alias')
        self._last = {}

    def _hash_plist(self, path):
        try:
            with open(path,'rb') as f: data = f.read()
            return hashlib.sha256(data).hexdigest()
        except Exception: return None

    def _snapshot(self):
        snap = {}
        for base in self.PATHS:
            for p in glob.glob(os.path.join(base, '*.plist')):
                info = {'path': p, 'hash': self._hash_plist(p)}
                try:
                    with open(p,'rb') as f:
                        pl = plistlib.load(f)
                    info.update({
                        'Label': pl.get('Label'),
                        'Program': pl.get('Program'),
                        'ProgramArguments': pl.get('ProgramArguments'),
                        'RunAtLoad': pl.get('RunAtLoad'),
                        'KeepAlive': pl.get('KeepAlive'),
                        'WatchPaths': pl.get('WatchPaths'),
                        'UserName': pl.get('UserName')
                    })
                except Exception:
                    pass
                snap[p] = info
        return snap

    def run(self):
        while not self.stop_event.is_set():
            now = time.time()
            cur = self._snapshot()
            added = {k:v for k,v in cur.items() if k not in self._last}
            removed = {k:v for k,v in self._last.items() if k not in cur}
            changed = {k:v for k,v in cur.items() if k in self._last and v.get('hash') != self._last[k].get('hash')}
            for kind, payload in (('added', added), ('removed', removed), ('changed', changed)):
                if not payload: continue
                event = {'type':'macos_launchd','event_type':kind,'timestamp':now,'items':payload,
                         'index':self.index,'host':self.host,'source':self.source,'sourcetype':self.sourcetype}
                if self.db_alias: event['db_alias']=self.db_alias
                self.event_queue.put(event)
            self._last = cur
            time.sleep(self.poll_interval)