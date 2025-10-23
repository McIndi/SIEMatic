"""
TailPlugin: Tails files and sends new lines to event_queue, handling log rotation.
"""

import glob
from pathlib import Path
import hashlib
import time
import logging
logger = logging.getLogger(__name__)
logger.debug("agent.plugins.tail_plugin module loaded.")

class TailPlugin:
    """
    Tails one or more files, following log rotation by name. Sends new lines to event_queue.
    Config keys:
      - patterns: list of glob patterns or absolute paths
      - poll_interval: seconds between checks (default: 1.0)
    """
    def __init__(self, config, event_queue, stop_event):
        self.patterns = config.get('patterns', [])
        if isinstance(self.patterns, str):
            self.patterns = [self.patterns]
        self.poll_interval = float(config.get('poll_interval', 1.0))
        self.event_queue = event_queue
        self.stop_event = stop_event
        self.seek_from_end = config.get('seek_from_end', True)
        self.file_positions = {}  # {str(path): offset}
        self.file_hashes = {}     # {str(path): hash}
        self.files = set()
        self.index = config.get('index', 'default')
        self.host = config.get('host', 'localhost')
        self.source = config.get('source', 'tail')
        self.sourcetype = config.get('sourcetype', 'text')
        self.db_alias = config.get('db_alias', None)
        logger.info("TailPlugin initialized with patterns=%s, poll_interval=%s", self.patterns, self.poll_interval)

    def _resolve_files(self):
        files = set()
        for pattern in self.patterns:
            for filename in glob.iglob(pattern, recursive=True):
                p = Path(filename).absolute()
                if p.is_file():
                    files.add(str(p))
        logger.debug("Resolved files: %s", files)
        return files

    def _init_file(self, filename):
        p = Path(filename)
        # Wait for file to exist and reach a minimum size
        while not p.exists() or p.stat().st_size < 1:
            time.sleep(0.1)
        with p.open('rb') as f:
            h = hashlib.sha256(f.read(256)).hexdigest()
        self.file_positions[filename] = p.stat().st_size if self.seek_from_end else 0
        self.file_hashes[filename] = h
        logger.info("Initialized file %s with hash %s, pos %s", filename, h, self.file_positions[filename])

    def run(self):
        logger.info("TailPlugin run started.")
        # Initial file discovery
        self.files = self._resolve_files()
        for filename in self.files:
            if filename not in self.file_positions:
                self._init_file(filename)
        while not self.stop_event.is_set():
            # Refresh file list (handle new files, log rotation)
            current_files = self._resolve_files()
            for filename in current_files:
                if filename not in self.file_positions:
                    self._init_file(filename)
            for filename in list(self.file_positions.keys()):
                p = Path(filename)
                try:
                    size = p.stat().st_size
                except Exception:
                    logger.warning("File missing or inaccessible: %s", filename)
                    continue
                pos = self.file_positions[filename]
                if pos > size:
                    # Log rotated, reset position and hash
                    self._init_file(filename)
                    pos = 0
                if pos == size:
                    continue
                with p.open('r', encoding='utf-8', errors='replace') as fin:
                    fin.seek(pos)
                    while True:
                        line = fin.readline()
                        if not line:
                            break
                        if not line.endswith('\n') and not line.endswith('\r'):
                            # Wait for full line
                            time.sleep(0.1)
                            continue
                        event = {
                            'src_path': filename,
                            'event_type': 'line',
                            'line': line,
                            'timestamp': time.time(),
                            'index': self.index,
                            'host': self.host,
                            'source': self.source,
                            'sourcetype': self.sourcetype
                        }
                        if self.db_alias:
                            event['db_alias'] = self.db_alias
                        self.event_queue.put(event)
                        pos = fin.tell()
                self.file_positions[filename] = pos
            time.sleep(self.poll_interval)
