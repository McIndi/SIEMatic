"""Run SIEMatic's local web, indexer, and telemetry agent stack."""

import os
from pathlib import Path
import secrets
import socket
import ssl
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

import psutil
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from project.signals import AGENT_GROUP_NAME
from tools.gen_dev_cert import DEFAULT_NAMES, generate_certificate


DEV_AGENT_USERNAME = 'siematic-dev-agent'
DEV_SUPERUSER_USERNAME = 'siematic-admin'
DEV_SUPERUSER_CREDENTIALS_FILENAME = 'rundev-superuser.txt'
DEFAULT_WEB_PORT = 8000
DEFAULT_INDEXER_PORT = 8001


class _WindowsProcessJob:
    """Keep child processes in a kill-on-close Windows Job Object.

    Process-tree enumeration is inherently racy: a child can outlive and be
    reparented away from the process that ``Popen`` returned.  A Job Object is
    maintained by Windows itself and therefore still tears down every assigned
    descendant if the rundev supervisor exits before its ``finally`` block can
    finish.
    """

    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ('ReadOperationCount', ctypes.c_ulonglong),
                ('WriteOperationCount', ctypes.c_ulonglong),
                ('OtherOperationCount', ctypes.c_ulonglong),
                ('ReadTransferCount', ctypes.c_ulonglong),
                ('WriteTransferCount', ctypes.c_ulonglong),
                ('OtherTransferCount', ctypes.c_ulonglong),
            ]

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ('PerProcessUserTimeLimit', ctypes.c_longlong),
                ('PerJobUserTimeLimit', ctypes.c_longlong),
                ('LimitFlags', wintypes.DWORD),
                ('MinimumWorkingSetSize', ctypes.c_size_t),
                ('MaximumWorkingSetSize', ctypes.c_size_t),
                ('ActiveProcessLimit', wintypes.DWORD),
                ('Affinity', ctypes.c_size_t),
                ('PriorityClass', wintypes.DWORD),
                ('SchedulingClass', wintypes.DWORD),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ('BasicLimitInformation', JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ('IoInfo', IO_COUNTERS),
                ('ProcessMemoryLimit', ctypes.c_size_t),
                ('JobMemoryLimit', ctypes.c_size_t),
                ('PeakProcessMemoryUsed', ctypes.c_size_t),
                ('PeakJobMemoryUsed', ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        )
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = (
            wintypes.HANDLE,
            wintypes.HANDLE,
        )
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())

        information = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        information.BasicLimitInformation.LimitFlags = (
            self._JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
        if not kernel32.SetInformationJobObject(
            handle,
            self._JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(information),
            ctypes.sizeof(information),
        ):
            error = ctypes.get_last_error()
            kernel32.CloseHandle(handle)
            raise ctypes.WinError(error)

        self._handle = handle
        self._kernel32 = kernel32

    def assign(self, process):
        import ctypes
        from ctypes import wintypes

        if not self._kernel32.AssignProcessToJobObject(
            self._handle,
            wintypes.HANDLE(process._handle),
        ):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self._handle is not None:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None


class Command(BaseCommand):
    help = (
        'Start the HTTPS web server, TLS indexer, and core telemetry agent '
        'against the local SQLite database. Create a development superuser '
        f'and write its credentials to {DEV_SUPERUSER_CREDENTIALS_FILENAME}.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--web-port', type=int, default=DEFAULT_WEB_PORT)
        parser.add_argument('--indexer-port', type=int, default=DEFAULT_INDEXER_PORT)

    def handle(self, *args, **options):
        self._force_line_buffering()
        self._validate_environment(options)
        project_root = Path(settings.BASE_DIR)
        cert_path = project_root / 'certs' / 'siematic.crt'
        key_path = project_root / 'certs' / 'siematic.key'
        self._ensure_certificate(cert_path, key_path)

        self.stdout.write('Applying SQLite migrations...')
        call_command('migrate', interactive=False, verbosity=options['verbosity'])

        superuser_password = secrets.token_urlsafe(32)
        self._configure_superuser(superuser_password)
        credentials_path = project_root / DEV_SUPERUSER_CREDENTIALS_FILENAME
        self._write_superuser_credentials(
            credentials_path,
            superuser_password,
            options['web_port'],
        )
        self.stdout.write(self.style.SUCCESS(
            f'Development superuser credentials written to {credentials_path}'
        ))

        self.stdout.write('Seeding default saved searches and dashboards...')
        call_command('seed_default_content', owner=DEV_SUPERUSER_USERNAME, verbosity=options['verbosity'])

        self.stdout.write('Collecting static assets...')
        call_command('collectstatic', interactive=False, verbosity=0)

        agent_password = secrets.token_urlsafe(32)
        self._configure_agent_user(agent_password)

        child_env = self._base_child_environment()
        process_job = self._create_process_job()
        processes = []
        try:
            indexer_env = {
                **child_env,
                'DJANGO_SETTINGS_MODULE': 'SIEMatic.settings.indexer',
                'INDEXER_HOSTNAME': '127.0.0.1',
                'INDEXER_PORT': str(options['indexer_port']),
                # Daphne/Twisted endpoint strings treat the colon in an
                # absolute Windows drive path as endpoint syntax. The child
                # runs from BASE_DIR, so portable relative paths avoid that
                # ambiguity.
                'INDEXER_SSL_CERT': str(cert_path.relative_to(project_root)),
                'INDEXER_SSL_KEY': str(key_path.relative_to(project_root)),
            }
            indexer = self._start(
                'indexer',
                ['indexer'],
                indexer_env,
                project_root,
                process_job,
            )
            processes.append(('indexer', indexer))
            self._wait_for_https(
                'indexer',
                options['indexer_port'],
                cert_path,
                indexer,
            )

            web_env = {
                **child_env,
                'DJANGO_SETTINGS_MODULE': 'SIEMatic.settings.web',
                'CHERRYPY_HOST': '127.0.0.1',
                'CHERRYPY_PORT': str(options['web_port']),
                'CHERRYPY_SSL': 'True',
                'CHERRYPY_SSL_CERT': str(cert_path),
                'CHERRYPY_SSL_KEY': str(key_path),
                # CherryPy's own autoreloader doesn't restart in place on
                # Windows (no execv-style process replacement); it spawns a
                # detached replacement process and lets this one exit. rundev
                # already supervises this process externally via _supervise(),
                # so that exit looks like a crash and takes indexer/agent down
                # with it. rundev has no code-reload story of its own: restart
                # rundev after backend changes.
                'CHERRYPY_AUTORELOAD': 'False',
            }
            web = self._start('web', ['serve'], web_env, project_root, process_job)
            processes.append(('web', web))
            self._wait_for_https('web', options['web_port'], cert_path, web)

            agent_env = {
                **child_env,
                'DJANGO_SETTINGS_MODULE': 'SIEMatic.settings.agent',
                'INDEXER_HOSTNAME': 'localhost',
                'INDEXER_PORT': str(options['indexer_port']),
                'INDEXER_TLS': 'True',
                'INDEXER_CA_BUNDLE': str(cert_path),
                'INDEXER_USERNAME': DEV_AGENT_USERNAME,
                'INDEXER_PASSWORD': agent_password,
                'SIEMATIC_AGENT_CORE_ONLY': 'True',
            }
            agent = self._start('agent', ['agent'], agent_env, project_root, process_job)
            processes.append(('agent', agent))

            self.stdout.write(self.style.SUCCESS(
                f'SIEMatic is running at https://localhost:{options["web_port"]}/'
            ))
            self.stdout.write(
                'System and network-security telemetry will begin arriving '
                'within a few seconds.'
            )
            self.stdout.write(
                f'Sign in as {DEV_SUPERUSER_USERNAME} with the password in '
                f'{credentials_path}.'
            )
            self.stdout.write('Press Ctrl+C to stop the complete process tree.')
            self._supervise(processes)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\nStopping SIEMatic...'))
        finally:
            try:
                for label, process in reversed(processes):
                    self._stop_process_tree(label, process)
            finally:
                if process_job is not None:
                    process_job.close()

    def _force_line_buffering(self):
        """Flush status messages promptly even when stdout isn't a TTY.

        Python fully block-buffers stdout/stderr when they aren't attached
        to a terminal (redirected to a file, piped, run under Docker or
        nohup). Since this command blocks forever in ``_supervise``, that
        buffering means readiness messages like "Web is ready." would never
        reach anyone watching non-interactively.
        """
        for stream in (sys.stdout, sys.stderr):
            reconfigure = getattr(stream, 'reconfigure', None)
            if reconfigure is not None:
                try:
                    reconfigure(line_buffering=True)
                except (ValueError, OSError):
                    pass

    def _validate_environment(self, options):
        engine = settings.DATABASES['default']['ENGINE']
        if engine != 'django.db.backends.sqlite3':
            raise CommandError(
                f'rundev requires SQLite, but the configured engine is {engine}.'
            )
        if options['web_port'] == options['indexer_port']:
            raise CommandError('The web and indexer ports must be different.')
        for name in ('web_port', 'indexer_port'):
            port = options[name]
            if not 1 <= port <= 65535:
                raise CommandError(f'--{name.replace("_", "-")} must be 1-65535.')

    def _ensure_certificate(self, cert_path, key_path):
        if cert_path.is_file() and key_path.is_file():
            self.stdout.write(f'Using development certificate {cert_path}')
            return
        if cert_path.exists() or key_path.exists():
            raise CommandError(
                'The development certificate pair is incomplete. Remove or repair '
                f'{cert_path.parent}, then run rundev again.'
            )

        names = list(dict.fromkeys((*DEFAULT_NAMES, socket.gethostname())))
        generate_certificate(cert_path, key_path, names)
        self.stdout.write(self.style.SUCCESS(
            f'Generated development certificate {cert_path}'
        ))

    def _configure_agent_user(self, password):
        user_model = get_user_model()
        user, _created = user_model.objects.get_or_create(
            username=DEV_AGENT_USERNAME,
            defaults={'is_active': True},
        )
        user.is_active = True
        user.set_password(password)
        user.save(update_fields=['is_active', 'password'])
        try:
            agent_group = Group.objects.get(name=AGENT_GROUP_NAME)
        except Group.DoesNotExist as exc:
            raise CommandError(
                'The Agent group was not created by migrations.'
            ) from exc
        user.groups.add(agent_group)

    def _configure_superuser(self, password):
        user_model = get_user_model()
        user, _created = user_model.objects.get_or_create(
            username=DEV_SUPERUSER_USERNAME,
        )
        user.is_active = True
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save(update_fields=[
            'is_active',
            'is_staff',
            'is_superuser',
            'password',
        ])

    def _write_superuser_credentials(self, path, password, web_port):
        contents = (
            f'URL=https://localhost:{web_port}/admin/\n'
            f'USERNAME={DEV_SUPERUSER_USERNAME}\n'
            f'PASSWORD={password}\n'
        )
        try:
            path.write_text(contents, encoding='utf-8')
            path.chmod(0o600)
        except OSError as exc:
            raise CommandError(
                'Could not write development superuser credentials to '
                f'{path}: {exc}'
            ) from exc

    def _base_child_environment(self):
        environment = os.environ.copy()
        environment.update({
            'DATABASE_ENGINE': 'django.db.backends.sqlite3',
            'DATABASE_NAME': str(settings.DATABASES['default']['NAME']),
            'DJANGO_ALLOWED_HOSTS': 'localhost,127.0.0.1,::1',
            'DJANGO_DEBUG': 'True',
            'SIEMATIC_TLS_ENABLED': 'True',
        })
        for name in (
            'DATABASE_USER',
            'DATABASE_PASSWORD',
            'DATABASE_HOST',
            'DATABASE_PORT',
        ):
            environment.pop(name, None)
        return environment

    def _create_process_job(self):
        if os.name != 'nt':
            return None
        try:
            return _WindowsProcessJob()
        except OSError as exc:
            raise CommandError(
                f'Could not create the Windows process supervisor: {exc}'
            ) from exc

    def _start(self, label, command, environment, project_root, process_job=None):
        full_command = [sys.executable, str(project_root / 'manage.py'), *command]
        popen_options = {
            'cwd': project_root,
            'env': environment,
        }
        if os.name == 'nt':
            popen_options['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_options['start_new_session'] = True
        self.stdout.write(f'Starting {label}...')
        process = subprocess.Popen(full_command, **popen_options)
        if process_job is not None:
            try:
                process_job.assign(process)
            except OSError as exc:
                process.kill()
                process.wait()
                raise CommandError(
                    f'Could not supervise the {label} process: {exc}'
                ) from exc
        return process

    def _wait_for_https(self, label, port, cert_path, process, timeout=30):
        context = ssl.create_default_context(cafile=str(cert_path))
        url = f'https://localhost:{port}/login/'
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            return_code = process.poll()
            if return_code is not None:
                raise CommandError(f'{label} exited with code {return_code}.')
            try:
                with urlopen(url, context=context, timeout=1):
                    self.stdout.write(self.style.SUCCESS(f'{label.capitalize()} is ready.'))
                    return
            except (OSError, URLError):
                time.sleep(0.25)
        raise CommandError(f'Timed out waiting for {label} at {url}.')

    def _supervise(self, processes):
        while True:
            for label, process in processes:
                return_code = process.poll()
                if return_code is not None:
                    raise CommandError(
                        f'{label} exited unexpectedly with code {return_code}.'
                    )
            time.sleep(0.5)

    def _stop_process_tree(self, label, process):
        if process.poll() is not None:
            return
        try:
            parent = psutil.Process(process.pid)
            targets = parent.children(recursive=True)
            targets.append(parent)
            for target in targets:
                try:
                    target.terminate()
                except psutil.NoSuchProcess:
                    pass
            _gone, alive = psutil.wait_procs(targets, timeout=5)
            for target in alive:
                try:
                    target.kill()
                except psutil.NoSuchProcess:
                    pass
            if alive:
                psutil.wait_procs(alive, timeout=2)
        except psutil.NoSuchProcess:
            pass
        finally:
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
        self.stdout.write(f'Stopped {label}.')
