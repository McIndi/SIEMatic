"""Cross-platform network exposure and connection telemetry."""

import ipaddress
import logging
import socket
import time

import psutil


logger = logging.getLogger(__name__)


class NetworkSecurityPlugin:
    """Report changes to Internet listeners and active connections.

    The collector uses psutil's system-wide connection API so the same code
    runs on Windows, Linux, and macOS. Process details are best effort because
    operating-system permissions can prevent attribution for some sockets.
    """

    def __init__(self, config, event_queue, stop_event):
        self.event_queue = event_queue
        self.stop_event = stop_event
        self.poll_interval = float(config.get('poll_interval', 30.0))
        self.status_interval = float(config.get('status_interval', 300.0))
        if self.poll_interval <= 0:
            raise ValueError('poll_interval must be greater than zero')
        if self.status_interval <= 0:
            raise ValueError('status_interval must be greater than zero')

        self.include_cmdline = bool(config.get('include_cmdline', False))
        self.index = config.get('index', 'network_security')
        self.host = config.get('host', 'localhost')
        self.source = config.get('source', 'network_security')
        self.sourcetype = config.get('sourcetype', 'json')
        self.db_alias = config.get('db_alias')

        self._last_listeners = {}
        self._last_connections = {}
        self._last_status_emit = None
        self._last_health = None

    @staticmethod
    def _endpoint(value):
        if not value:
            return None
        address = getattr(value, 'ip', value[0])
        port = getattr(value, 'port', value[1])
        return {'address': str(address), 'port': int(port)}

    @staticmethod
    def _address_scope(address):
        if address in ('0.0.0.0', '::'):
            return 'wildcard'
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            return 'unknown'
        if parsed.is_loopback:
            return 'loopback'
        if parsed.is_link_local:
            return 'link_local'
        if parsed.is_multicast:
            return 'multicast'
        if parsed.is_private:
            return 'private'
        if parsed.is_global:
            return 'public'
        return 'special'

    @staticmethod
    def _family_name(family):
        if family == socket.AF_INET:
            return 'ipv4'
        if family == socket.AF_INET6:
            return 'ipv6'
        return str(getattr(family, 'name', family)).lower()

    @staticmethod
    def _protocol_name(socket_type):
        if socket_type == socket.SOCK_STREAM:
            return 'tcp'
        if socket_type == socket.SOCK_DGRAM:
            return 'udp'
        return str(getattr(socket_type, 'name', socket_type)).lower()

    def _process_details(self, pid, cache, counters):
        if pid is None:
            return {
                'process_name': None,
                'process_exe': None,
                'process_user': None,
                'process_cmdline': None,
            }
        if pid in cache:
            return cache[pid]

        details = {
            'process_name': None,
            'process_exe': None,
            'process_user': None,
            'process_cmdline': None,
        }
        inaccessible = False
        try:
            process = psutil.Process(pid)
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            counters['processes_unavailable'] += 1
            cache[pid] = details
            return details

        getters = {
            'process_name': process.name,
            'process_exe': process.exe,
            'process_user': process.username,
        }
        if self.include_cmdline:
            getters['process_cmdline'] = process.cmdline

        for field, getter in getters.items():
            try:
                details[field] = getter()
            except psutil.AccessDenied:
                inaccessible = True
            except (psutil.NoSuchProcess, psutil.ZombieProcess, OSError):
                counters['processes_unavailable'] += 1
                break
        if inaccessible:
            counters['processes_access_denied'] += 1
        cache[pid] = details
        return details

    def _record(self, connection, process_cache, counters):
        local = self._endpoint(connection.laddr)
        remote = self._endpoint(connection.raddr)
        protocol = self._protocol_name(connection.type)
        status = str(connection.status or 'NONE').upper()
        record = {
            'protocol': protocol,
            'address_family': self._family_name(connection.family),
            'local_address': local['address'],
            'local_port': local['port'],
            'local_scope': self._address_scope(local['address']),
            'remote_address': remote['address'] if remote else None,
            'remote_port': remote['port'] if remote else None,
            'remote_scope': self._address_scope(remote['address']) if remote else None,
            'status': status,
            'pid': connection.pid,
        }
        record.update(self._process_details(connection.pid, process_cache, counters))
        is_listener = (
            status == str(psutil.CONN_LISTEN).upper()
            or (protocol == 'udp' and remote is None)
        )
        return record, is_listener

    @staticmethod
    def _identity(record, listener):
        values = [
            record['protocol'],
            record['address_family'],
            record['local_address'],
            record['local_port'],
            record['pid'],
        ]
        if not listener:
            values.extend((record['remote_address'], record['remote_port']))
        return tuple(values)

    def _snapshot(self):
        listeners = {}
        connections = {}
        process_cache = {}
        counters = {
            'processes_access_denied': 0,
            'processes_unavailable': 0,
        }
        for connection in psutil.net_connections(kind='inet'):
            if not connection.laddr:
                continue
            record, is_listener = self._record(
                connection,
                process_cache,
                counters,
            )
            if is_listener:
                listeners[self._identity(record, True)] = record
            elif connection.raddr:
                connections[self._identity(record, False)] = record
        return listeners, connections, counters

    def _queue_event(self, event_type, timestamp, data, previous=None):
        event = {
            'type': 'network_security',
            'event_type': event_type,
            'timestamp': timestamp,
            'data': data,
            'index': self.index,
            'host': self.host,
            'source': self.source,
            'sourcetype': self.sourcetype,
        }
        if previous is not None:
            event['previous'] = previous
        if self.db_alias:
            event['db_alias'] = self.db_alias
        self.event_queue.put(event)

    def _emit_changes(self, timestamp, current, previous, event_names):
        added_name, removed_name, changed_name = event_names
        for identity in sorted(current.keys() - previous.keys(), key=repr):
            self._queue_event(added_name, timestamp, current[identity])
        for identity in sorted(previous.keys() - current.keys(), key=repr):
            self._queue_event(removed_name, timestamp, previous[identity])
        for identity in sorted(current.keys() & previous.keys(), key=repr):
            if current[identity] != previous[identity]:
                self._queue_event(
                    changed_name,
                    timestamp,
                    current[identity],
                    previous=previous[identity],
                )

    def _emit_status(self, timestamp, status):
        health = (
            status['state'],
            status.get('error'),
            status.get('processes_access_denied', 0) > 0,
            status.get('processes_unavailable', 0) > 0,
        )
        due = (
            self._last_status_emit is None
            or timestamp - self._last_status_emit >= self.status_interval
        )
        if due or health != self._last_health:
            self._queue_event('collection_status', timestamp, status)
            self._last_status_emit = timestamp
            self._last_health = health

    def collect_once(self, timestamp=None):
        """Collect and enqueue one snapshot. Exposed for deterministic tests."""
        timestamp = time.time() if timestamp is None else timestamp
        started = time.monotonic()
        try:
            listeners, connections, counters = self._snapshot()
        except (psutil.Error, OSError) as exc:
            logger.warning('Network connection collection failed: %s', exc)
            self._emit_status(
                timestamp,
                {
                    'state': 'error',
                    'error': f'{type(exc).__name__}: {exc}',
                    'collection_duration_ms': round(
                        (time.monotonic() - started) * 1000,
                        3,
                    ),
                },
            )
            return

        self._emit_changes(
            timestamp,
            listeners,
            self._last_listeners,
            ('listener_added', 'listener_removed', 'listener_changed'),
        )
        self._emit_changes(
            timestamp,
            connections,
            self._last_connections,
            ('connection_opened', 'connection_closed', 'connection_changed'),
        )
        self._last_listeners = listeners
        self._last_connections = connections

        state = 'partial' if any(counters.values()) else 'ok'
        self._emit_status(
            timestamp,
            {
                'state': state,
                'listener_count': len(listeners),
                'connection_count': len(connections),
                'processes_access_denied': counters['processes_access_denied'],
                'processes_unavailable': counters['processes_unavailable'],
                'include_cmdline': self.include_cmdline,
                'collection_duration_ms': round(
                    (time.monotonic() - started) * 1000,
                    3,
                ),
            },
        )

    def run(self):
        logger.info(
            'NetworkSecurityPlugin started with poll_interval=%s',
            self.poll_interval,
        )
        while not self.stop_event.is_set():
            self.collect_once()
            self.stop_event.wait(self.poll_interval)
