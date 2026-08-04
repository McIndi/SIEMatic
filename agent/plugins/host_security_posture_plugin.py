"""Cross-platform host security posture inventory."""

import getpass
import glob
import json
import logging
import os
import platform
import shutil
import socket
import subprocess
import time
from datetime import datetime

import psutil


logger = logging.getLogger(__name__)


class HostSecurityPosturePlugin:
    """Collect stable host inventory and best-effort security-control state.

    Portable data comes from Python and psutil. Small platform adapters add
    firewall, disk-encryption, secure-boot, and endpoint-protection state when
    the operating system exposes it. Missing tools or insufficient privileges
    are represented as ``unknown`` instead of stopping the collector.
    """

    def __init__(self, config, event_queue, stop_event):
        self.event_queue = event_queue
        self.stop_event = stop_event
        self.poll_interval = float(config.get('poll_interval', 900.0))
        self.status_interval = float(config.get('status_interval', 3600.0))
        self.command_timeout = float(config.get('command_timeout', 10.0))
        if self.poll_interval <= 0:
            raise ValueError('poll_interval must be greater than zero')
        if self.status_interval <= 0:
            raise ValueError('status_interval must be greater than zero')
        if self.command_timeout <= 0:
            raise ValueError('command_timeout must be greater than zero')

        self.collect_local_accounts = bool(
            config.get('collect_local_accounts', True)
        )
        self.index = config.get('index', 'host_security_posture')
        self.host = config.get('host', socket.gethostname())
        self.source = config.get('source', 'host_security_posture')
        self.sourcetype = config.get('sourcetype', 'json')
        self.db_alias = config.get('db_alias')

        self._last_snapshot = {}
        self._last_status_emit = None
        self._last_health = None

    @staticmethod
    def _is_privileged():
        if os.name == 'nt':
            try:
                import ctypes

                return bool(ctypes.windll.shell32.IsUserAnAdmin())
            except (AttributeError, OSError):
                return None
        geteuid = getattr(os, 'geteuid', None)
        return geteuid() == 0 if geteuid is not None else None

    def _collect_host_identity(self):
        uname = platform.uname()
        return {
            'hostname': socket.gethostname(),
            'fqdn': socket.getfqdn(),
            'os': uname.system,
            'os_release': uname.release,
            'os_version': uname.version,
            'architecture': uname.machine,
            'processor': uname.processor or None,
            'boot_time': psutil.boot_time(),
            'timezone': datetime.now().astimezone().tzname(),
            'agent_user': getpass.getuser(),
            'agent_privileged': self._is_privileged(),
        }

    @staticmethod
    def _address_family_name(family):
        if family == socket.AF_INET:
            return 'ipv4'
        if family == socket.AF_INET6:
            return 'ipv6'
        if family == psutil.AF_LINK:
            return 'mac'
        return str(getattr(family, 'name', family)).lower()

    def _collect_network_interfaces(self):
        addresses = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        interfaces = []
        for name in sorted(set(addresses) | set(stats)):
            interface_stats = stats.get(name)
            interface_addresses = []
            for address in addresses.get(name, []):
                interface_addresses.append({
                    'family': self._address_family_name(address.family),
                    'address': address.address,
                    'netmask': address.netmask,
                    'broadcast': address.broadcast,
                    'ptp': address.ptp,
                })
            interface_addresses.sort(
                key=lambda item: (item['family'], item['address'] or '')
            )
            duplex = None
            if interface_stats is not None:
                duplex_names = {
                    psutil.NIC_DUPLEX_FULL: 'full',
                    psutil.NIC_DUPLEX_HALF: 'half',
                    psutil.NIC_DUPLEX_UNKNOWN: 'unknown',
                }
                duplex = duplex_names.get(interface_stats.duplex, 'unknown')
            interfaces.append({
                'name': name,
                'is_up': interface_stats.isup if interface_stats else None,
                'duplex': duplex,
                'speed_mbps': interface_stats.speed if interface_stats else None,
                'mtu': interface_stats.mtu if interface_stats else None,
                'addresses': interface_addresses,
            })
        return interfaces

    @staticmethod
    def _collect_user_sessions():
        sessions = []
        for user in psutil.users():
            sessions.append({
                'username': user.name,
                'terminal': user.terminal,
                'remote_host': user.host,
                'started': user.started,
                'pid': getattr(user, 'pid', None),
            })
        return sorted(
            sessions,
            key=lambda item: (
                item['username'] or '',
                item['terminal'] or '',
                item['started'] or 0,
            ),
        )

    @staticmethod
    def _collect_filesystems():
        filesystems = []
        for partition in psutil.disk_partitions(all=False):
            filesystems.append({
                'device': partition.device,
                'mountpoint': partition.mountpoint,
                'filesystem': partition.fstype,
                'options': sorted(
                    option
                    for option in (partition.opts or '').split(',')
                    if option
                ),
            })
        return sorted(
            filesystems,
            key=lambda item: (item['mountpoint'], item['device']),
        )

    def _run(self, command):
        options = {
            'capture_output': True,
            'text': True,
            'errors': 'replace',
            'timeout': self.command_timeout,
            'check': False,
        }
        if os.name == 'nt':
            options['creationflags'] = getattr(
                subprocess,
                'CREATE_NO_WINDOW',
                0,
            )
        completed = subprocess.run(command, **options)
        if completed.returncode != 0:
            raise OSError(
                f'{command[0]} exited with status {completed.returncode}'
            )
        return completed.stdout.strip()

    def _powershell_json(self, script):
        executable = shutil.which('powershell.exe') or shutil.which('pwsh.exe')
        if not executable:
            raise FileNotFoundError('PowerShell is unavailable')
        output = self._run([
            executable,
            '-NoLogo',
            '-NoProfile',
            '-NonInteractive',
            '-Command',
            script,
        ])
        return json.loads(output) if output else None

    def _collect_windows_accounts(self):
        script = r'''
$items = @(Get-LocalUser | ForEach-Object {
    [ordered]@{
        username = $_.Name
        enabled = [bool]$_.Enabled
        sid = [string]$_.SID
        last_logon = if ($_.LastLogon) { $_.LastLogon.ToString('o') } else { $null }
        password_expires = if ($_.PasswordExpires) { $_.PasswordExpires.ToString('o') } else { $null }
        password_required = [bool]$_.PasswordRequired
        user_may_change_password = [bool]$_.UserMayChangePassword
    }
})
ConvertTo-Json -InputObject $items -Depth 4 -Compress
'''
        result = self._powershell_json(script)
        if result is None:
            return []
        accounts = result if isinstance(result, list) else [result]
        return sorted(accounts, key=lambda item: item.get('username') or '')

    @staticmethod
    def _collect_posix_accounts():
        import pwd

        accounts = []
        for account in pwd.getpwall():
            accounts.append({
                'username': account.pw_name,
                'uid': account.pw_uid,
                'gid': account.pw_gid,
                'home': account.pw_dir,
                'shell': account.pw_shell,
                'system_account': account.pw_uid < 1000,
            })
        return sorted(accounts, key=lambda item: (item['uid'], item['username']))

    def _collect_local_account_inventory(self):
        if platform.system() == 'Windows':
            return self._collect_windows_accounts()
        return self._collect_posix_accounts()

    def _collect_windows_controls(self):
        script = r'''
$result = [ordered]@{}
try {
    $result.firewall = [ordered]@{
        state = 'available'
        profiles = @(Get-NetFirewallProfile | ForEach-Object {
            [ordered]@{
                name = $_.Name
                enabled = [bool]$_.Enabled
                default_inbound = [string]$_.DefaultInboundAction
                default_outbound = [string]$_.DefaultOutboundAction
            }
        })
    }
} catch { $result.firewall = [ordered]@{ state = 'unknown' } }
if (Get-Command Get-MpComputerStatus -ErrorAction SilentlyContinue) {
    try {
        $mp = Get-MpComputerStatus
        $result.endpoint_protection = [ordered]@{
            provider = 'Microsoft Defender'
            state = 'available'
            antivirus_enabled = [bool]$mp.AntivirusEnabled
            antispyware_enabled = [bool]$mp.AntispywareEnabled
            realtime_protection_enabled = [bool]$mp.RealTimeProtectionEnabled
            behavior_monitor_enabled = [bool]$mp.BehaviorMonitorEnabled
            signatures_last_updated = if ($mp.AntivirusSignatureLastUpdated) { $mp.AntivirusSignatureLastUpdated.ToString('o') } else { $null }
        }
    } catch { $result.endpoint_protection = [ordered]@{ provider = 'Microsoft Defender'; state = 'unknown' } }
} else { $result.endpoint_protection = [ordered]@{ state = 'unsupported' } }
try {
    $result.secure_boot = [ordered]@{
        state = 'available'
        enabled = [bool](Confirm-SecureBootUEFI -ErrorAction Stop)
    }
} catch { $result.secure_boot = [ordered]@{ state = 'unknown'; enabled = $null } }
if (Get-Command Get-BitLockerVolume -ErrorAction SilentlyContinue) {
    try {
        $result.disk_encryption = [ordered]@{
            provider = 'BitLocker'
            state = 'available'
            volumes = @(Get-BitLockerVolume | ForEach-Object {
                [ordered]@{
                    mount_point = $_.MountPoint
                    volume_status = [string]$_.VolumeStatus
                    protection_status = [string]$_.ProtectionStatus
                    encryption_method = [string]$_.EncryptionMethod
                    encryption_percentage = $_.EncryptionPercentage
                }
            })
        }
    } catch { $result.disk_encryption = [ordered]@{ provider = 'BitLocker'; state = 'unknown' } }
} else { $result.disk_encryption = [ordered]@{ provider = 'BitLocker'; state = 'unsupported' } }
ConvertTo-Json -InputObject $result -Depth 7 -Compress
'''
        controls = self._powershell_json(script) or {}
        firewall = controls.get('firewall') or {}
        if isinstance(firewall.get('profiles'), list):
            firewall['profiles'].sort(key=lambda item: item.get('name') or '')
        encryption = controls.get('disk_encryption') or {}
        if isinstance(encryption.get('volumes'), list):
            encryption['volumes'].sort(
                key=lambda item: item.get('mount_point') or ''
            )
        return controls

    def _linux_firewall(self):
        if shutil.which('ufw'):
            try:
                output = self._run(['ufw', 'status'])
                first_line = output.splitlines()[0] if output else ''
                status_value = first_line.partition(':')[2].strip().lower()
                return {
                    'provider': 'ufw',
                    'state': 'enabled' if status_value == 'active' else 'disabled',
                }
            except (OSError, subprocess.TimeoutExpired):
                return {'provider': 'ufw', 'state': 'unknown'}
        if shutil.which('firewall-cmd'):
            try:
                output = self._run(['firewall-cmd', '--state'])
                return {
                    'provider': 'firewalld',
                    'state': 'enabled' if output.lower() == 'running' else output.lower(),
                }
            except (OSError, subprocess.TimeoutExpired):
                return {'provider': 'firewalld', 'state': 'unknown'}
        if shutil.which('nft'):
            try:
                output = self._run(['nft', 'list', 'ruleset'])
                return {
                    'provider': 'nftables',
                    'state': 'configured' if output else 'empty',
                }
            except (OSError, subprocess.TimeoutExpired):
                return {'provider': 'nftables', 'state': 'unknown'}
        return {'provider': None, 'state': 'unsupported'}

    @staticmethod
    def _linux_secure_boot():
        paths = glob.glob('/sys/firmware/efi/efivars/SecureBoot-*')
        if not paths:
            return {'state': 'unsupported', 'enabled': None}
        try:
            with open(paths[0], 'rb') as secure_boot:
                value = secure_boot.read(5)
            return {
                'state': 'available',
                'enabled': len(value) >= 5 and value[4] == 1,
            }
        except OSError:
            return {'state': 'unknown', 'enabled': None}

    def _linux_disk_encryption(self):
        if not shutil.which('lsblk'):
            return {'provider': 'LUKS', 'state': 'unsupported'}
        try:
            output = self._run([
                'lsblk',
                '--json',
                '--output',
                'NAME,TYPE,FSTYPE,MOUNTPOINTS',
            ])
            devices = json.loads(output).get('blockdevices', [])
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            return {'provider': 'LUKS', 'state': 'unknown'}

        encrypted = []

        def walk(items):
            for item in items:
                if str(item.get('fstype') or '').lower() == 'crypto_luks':
                    encrypted.append(item.get('name'))
                walk(item.get('children') or [])

        walk(devices)
        return {
            'provider': 'LUKS',
            'state': 'detected' if encrypted else 'not_detected',
            'encrypted_devices': sorted(filter(None, encrypted)),
        }

    def _collect_linux_controls(self):
        return {
            'firewall': self._linux_firewall(),
            'secure_boot': self._linux_secure_boot(),
            'disk_encryption': self._linux_disk_encryption(),
            'endpoint_protection': {'state': 'not_assessed'},
        }

    def _macos_check(self, command, enabled_text):
        if not os.path.exists(command[0]):
            return {'state': 'unsupported', 'enabled': None}
        try:
            output = self._run(command)
            return {
                'state': 'available',
                'enabled': enabled_text in output.lower(),
                'summary': output.splitlines()[0] if output else '',
            }
        except (OSError, subprocess.TimeoutExpired):
            return {'state': 'unknown', 'enabled': None}

    def _collect_macos_controls(self):
        return {
            'firewall': self._macos_check(
                [
                    '/usr/libexec/ApplicationFirewall/socketfilterfw',
                    '--getglobalstate',
                ],
                'enabled',
            ),
            'disk_encryption': self._macos_check(
                ['/usr/bin/fdesetup', 'status'],
                'filevault is on',
            ),
            'gatekeeper': self._macos_check(
                ['/usr/sbin/spctl', '--status'],
                'assessments enabled',
            ),
            'secure_boot': {'state': 'not_assessed', 'enabled': None},
            'endpoint_protection': {'state': 'not_assessed'},
        }

    def _collect_security_controls(self):
        system = platform.system()
        if system == 'Windows':
            return self._collect_windows_controls()
        if system == 'Linux':
            return self._collect_linux_controls()
        if system == 'Darwin':
            return self._collect_macos_controls()
        return {
            'firewall': {'state': 'unsupported'},
            'disk_encryption': {'state': 'unsupported'},
            'secure_boot': {'state': 'unsupported'},
            'endpoint_protection': {'state': 'unsupported'},
        }

    def _collect_snapshot(self):
        collectors = [
            ('host_identity', self._collect_host_identity),
            ('network_interfaces', self._collect_network_interfaces),
            ('user_sessions', self._collect_user_sessions),
            ('filesystems', self._collect_filesystems),
            ('security_controls', self._collect_security_controls),
        ]
        if self.collect_local_accounts:
            collectors.append(
                ('local_accounts', self._collect_local_account_inventory)
            )

        snapshot = {}
        issues = []
        for component, collector in collectors:
            try:
                snapshot[component] = collector()
            except (
                OSError,
                psutil.Error,
                subprocess.TimeoutExpired,
                json.JSONDecodeError,
            ) as exc:
                logger.warning(
                    'Host posture component %s failed: %s',
                    component,
                    exc,
                )
                issues.append({
                    'component': component,
                    'error_type': type(exc).__name__,
                })
        return snapshot, issues

    def _queue_event(
        self,
        event_type,
        timestamp,
        component,
        data,
        previous=None,
    ):
        event = {
            'type': 'host_security_posture',
            'event_type': event_type,
            'timestamp': timestamp,
            'component': component,
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

    def _emit_status(self, timestamp, status):
        health = (
            status['state'],
            tuple(
                (issue['component'], issue['error_type'])
                for issue in status['issues']
            ),
        )
        due = (
            self._last_status_emit is None
            or timestamp - self._last_status_emit >= self.status_interval
        )
        if due or health != self._last_health:
            self._queue_event(
                'collection_status',
                timestamp,
                'collector',
                status,
            )
            self._last_status_emit = timestamp
            self._last_health = health

    def collect_once(self, timestamp=None):
        """Collect and enqueue one posture snapshot or its component diffs."""
        timestamp = time.time() if timestamp is None else timestamp
        started = time.monotonic()
        snapshot, issues = self._collect_snapshot()
        for component, current in snapshot.items():
            if component not in self._last_snapshot:
                self._queue_event(
                    'posture_snapshot',
                    timestamp,
                    component,
                    current,
                )
            elif current != self._last_snapshot[component]:
                self._queue_event(
                    'posture_changed',
                    timestamp,
                    component,
                    current,
                    previous=self._last_snapshot[component],
                )
            self._last_snapshot[component] = current

        self._emit_status(
            timestamp,
            {
                'state': 'partial' if issues else 'ok',
                'components_collected': sorted(snapshot),
                'components_failed': sorted(
                    issue['component'] for issue in issues
                ),
                'issues': issues,
                'collection_duration_ms': round(
                    (time.monotonic() - started) * 1000,
                    3,
                ),
            },
        )

    def run(self):
        logger.info(
            'HostSecurityPosturePlugin started with poll_interval=%s',
            self.poll_interval,
        )
        while not self.stop_event.is_set():
            self.collect_once()
            self.stop_event.wait(self.poll_interval)
