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
DEFAULT_WEB_PORT = 8000
DEFAULT_INDEXER_PORT = 8001


class Command(BaseCommand):
    help = (
        'Start the HTTPS web server, TLS indexer, and sysmon-only agent '
        'against the local SQLite database.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--web-port', type=int, default=DEFAULT_WEB_PORT)
        parser.add_argument('--indexer-port', type=int, default=DEFAULT_INDEXER_PORT)
        parser.add_argument(
            '--create-superuser',
            action='store_true',
            help='Interactively create an administrator before starting services.',
        )

    def handle(self, *args, **options):
        self._force_line_buffering()
        self._validate_environment(options)
        project_root = Path(settings.BASE_DIR)
        cert_path = project_root / 'certs' / 'siematic.crt'
        key_path = project_root / 'certs' / 'siematic.key'
        self._ensure_certificate(cert_path, key_path)

        self.stdout.write('Applying SQLite migrations...')
        call_command('migrate', interactive=False, verbosity=options['verbosity'])
        if options['create_superuser']:
            call_command('createsuperuser', interactive=True)
        self.stdout.write('Collecting static assets...')
        call_command('collectstatic', interactive=False, verbosity=0)

        agent_password = secrets.token_urlsafe(32)
        self._configure_agent_user(agent_password)

        child_env = self._base_child_environment()
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
                'CHERRYPY_AUTORELOAD': 'True',
            }
            web = self._start('web', ['serve'], web_env, project_root)
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
                'SIEMATIC_AGENT_SYSMON_ONLY': 'True',
            }
            agent = self._start('agent', ['agent'], agent_env, project_root)
            processes.append(('agent', agent))

            self.stdout.write(self.style.SUCCESS(
                f'SIEMatic is running at https://localhost:{options["web_port"]}/'
            ))
            self.stdout.write(
                'Sysmon host telemetry will begin arriving within a few seconds.'
            )
            self.stdout.write(
                'To provision an administrator, restart once with '
                '`python manage.py rundev --create-superuser`.'
            )
            self.stdout.write('Press Ctrl+C to stop the complete process tree.')
            self._supervise(processes)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\nStopping SIEMatic...'))
        finally:
            for label, process in reversed(processes):
                self._stop_process_tree(label, process)

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

    def _start(self, label, command, environment, project_root):
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
        return subprocess.Popen(full_command, **popen_options)

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
