"""
Tests for the project app.

This module contains unit tests for profiles, authentication, and default permissions.
"""
import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.forms.models import model_to_dict
from django.test import TestCase, Client
from django.urls import NoReverseMatch, reverse

from dashboarding.models import Dashboard, Panel
from events.models import Event
from project.management.commands.rundev import (
    Command as RundevCommand,
    DEV_SUPERUSER_USERNAME,
)
from search2.engine.core import parse_pipeline, run_pipeline
from search2.models import SavedSearch
from search2.utils import coerce_to_list_of_dicts
from tools.container_healthcheck import indexer_is_healthy, main, web_is_healthy

from .models import UserProfile


class ContainerHealthcheckTests(TestCase):
    @patch.dict(
        'tools.container_healthcheck.os.environ',
        {'SIEMATIC_TLS_ENABLED': 'True', 'CHERRYPY_PORT': '8443'},
        clear=True,
    )
    @patch('tools.container_healthcheck.urllib.request.urlopen')
    @patch('tools.container_healthcheck.ssl.create_default_context')
    def test_web_probe_uses_configured_tls_port(self, create_context, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.status = 200
        context = create_context.return_value

        self.assertTrue(web_is_healthy())

        urlopen.assert_called_once_with(
            'https://127.0.0.1:8443/accounts/login/',
            timeout=4,
            context=context,
        )

    @patch.dict(
        'tools.container_healthcheck.os.environ',
        {'INDEXER_PORT': '5443'},
        clear=True,
    )
    @patch('tools.container_healthcheck.socket.create_connection')
    def test_indexer_probe_uses_configured_port(self, create_connection):
        self.assertTrue(indexer_is_healthy())

        create_connection.assert_called_once_with(
            ('127.0.0.1', 5443),
            timeout=4,
        )

    @patch('tools.container_healthcheck.web_is_healthy', side_effect=OSError('down'))
    def test_failed_probe_returns_nonzero(self, web_probe):
        with patch('tools.container_healthcheck.sys.stderr', StringIO()):
            self.assertEqual(main(['web']), 1)


class RundevSuperuserTests(TestCase):
    def test_configure_superuser_creates_and_rotates_development_account(self):
        command = RundevCommand()

        command._configure_superuser('first-password')
        user = get_user_model().objects.get(username=DEV_SUPERUSER_USERNAME)

        self.assertTrue(user.is_active)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password('first-password'))

        command._configure_superuser('second-password')
        user.refresh_from_db()

        self.assertEqual(
            get_user_model().objects.filter(
                username=DEV_SUPERUSER_USERNAME,
            ).count(),
            1,
        )
        self.assertFalse(user.check_password('first-password'))
        self.assertTrue(user.check_password('second-password'))

    def test_write_superuser_credentials_records_login_details(self):
        command = RundevCommand()

        with TemporaryDirectory() as directory:
            path = Path(directory) / 'credentials.txt'
            command._write_superuser_credentials(path, 'random-password', 8443)

            self.assertEqual(
                path.read_text(encoding='utf-8'),
                'URL=https://localhost:8443/admin/\n'
                f'USERNAME={DEV_SUPERUSER_USERNAME}\n'
                'PASSWORD=random-password\n',
            )

    @patch('project.management.commands.rundev.subprocess.Popen')
    def test_start_assigns_child_to_process_job(self, popen):
        process = popen.return_value
        process_job = Mock()
        project_root = Path('project-root')

        result = RundevCommand()._start(
            'web',
            ['serve'],
            {'EXAMPLE': 'value'},
            project_root,
            process_job,
        )

        self.assertIs(result, process)
        process_job.assign.assert_called_once_with(process)


class SeedDefaultContentTests(TestCase):
    NETWORK_DASHBOARDS = {
        'Network Security Overview',
        'Listening Service Activity',
        'Public Connection Activity',
    }
    POSTURE_DASHBOARDS = {
        'Host Security Posture Overview',
        'Security Controls & Encryption',
        'Host Identity & Access Inventory',
    }

    def setUp(self):
        self.owner = get_user_model().objects.create_superuser(
            username=DEV_SUPERUSER_USERNAME,
            email='admin@example.invalid',
            password='testpass',
        )

    def test_seed_creates_expected_searches_and_dashboards(self):
        call_command('seed_default_content', owner=DEV_SUPERUSER_USERNAME)

        searches = SavedSearch.objects.filter(owner=self.owner)
        self.assertGreater(searches.count(), 0)
        for search in searches:
            self.assertTrue(search.is_public)
            # Every seeded query must at least be parseable as a pipeline.
            self.assertTrue(parse_pipeline(search.query))

        dashboards = Dashboard.objects.filter(created_by=self.owner)
        self.assertGreater(dashboards.count(), 0)
        self.assertTrue(
            (self.NETWORK_DASHBOARDS | self.POSTURE_DASHBOARDS).issubset(
                set(dashboards.values_list('name', flat=True))
            )
        )
        for dashboard in dashboards:
            panels = Panel.objects.filter(dashboard=dashboard)
            self.assertGreater(panels.count(), 0)
            for panel in panels:
                self.assertTrue(parse_pipeline(panel.search))
                if panel.visualization_type == 'chart':
                    self.assertTrue(panel.x_field)
                    self.assertTrue(panel.y_field)

    def test_network_dashboard_searches_execute_against_collected_event_shapes(self):
        listener = {
            'type': 'network_security',
            'event_type': 'listener_added',
            'data': {
                'protocol': 'tcp',
                'local_address': '0.0.0.0',
                'local_port': 8080,
                'local_scope': 'wildcard',
                'remote_address': None,
                'remote_port': None,
                'remote_scope': None,
                'status': 'LISTEN',
                'pid': 101,
                'process_name': 'example-server',
                'process_exe': '/opt/example-server',
                'process_user': 'service-user',
            },
        }
        connection = {
            'type': 'network_security',
            'event_type': 'connection_opened',
            'data': {
                'protocol': 'tcp',
                'local_address': '10.0.0.2',
                'local_port': 50123,
                'local_scope': 'private',
                'remote_address': '203.0.113.10',
                'remote_port': 443,
                'remote_scope': 'public',
                'status': 'ESTABLISHED',
                'pid': 202,
                'process_name': 'example-client',
                'process_exe': '/opt/example-client',
                'process_user': 'desktop-user',
            },
        }
        status = {
            'type': 'network_security',
            'event_type': 'collection_status',
            'data': {
                'state': 'ok',
                'listener_count': 1,
                'connection_count': 1,
                'processes_access_denied': 0,
                'processes_unavailable': 0,
                'collection_duration_ms': 12.5,
            },
        }
        for payload in (listener, connection, status):
            Event.objects.create(
                index='network_security',
                host='test-host',
                source='network_security',
                sourcetype='json',
                data=json.dumps(payload),
            )

        call_command('seed_default_content', owner=DEV_SUPERUSER_USERNAME)
        request = SimpleNamespace(user=self.owner)
        network_searches = SavedSearch.objects.filter(
            owner=self.owner,
            name__in={
                panel.search.removeprefix('run_saved_search ').strip('"')
                for dashboard in Dashboard.objects.filter(
                    created_by=self.owner,
                    name__in=self.NETWORK_DASHBOARDS,
                )
                for panel in dashboard.panels.all()
            },
        )

        self.assertEqual(network_searches.count(), 12)
        for saved_search in network_searches:
            result = run_pipeline(None, saved_search.query, request=request)
            rows = coerce_to_list_of_dicts(result)
            self.assertIsInstance(rows, list, saved_search.name)

    def test_posture_dashboard_searches_execute_against_collected_event_shapes(self):
        controls = {
            'firewall': {
                'state': 'available',
                'profiles': [{'name': 'Private', 'enabled': True}],
            },
            'secure_boot': {'state': 'available', 'enabled': True},
            'disk_encryption': {
                'provider': 'BitLocker',
                'state': 'available',
                'volumes': [{'mount_point': 'C:', 'protection_status': 'On'}],
            },
            'endpoint_protection': {
                'provider': 'Microsoft Defender',
                'state': 'available',
                'realtime_protection_enabled': True,
            },
        }
        components = {
            'host_identity': {
                'fqdn': 'host.example.invalid',
                'os': 'ExampleOS',
                'os_release': '1',
                'architecture': 'x86_64',
                'boot_time': 1000.0,
                'timezone': 'UTC',
                'agent_user': 'collector',
                'agent_privileged': False,
            },
            'network_interfaces': [
                {'name': 'eth0', 'is_up': True, 'addresses': []},
            ],
            'user_sessions': [
                {'username': 'alice', 'remote_host': '10.0.0.3'},
            ],
            'filesystems': [
                {'device': '/dev/sda1', 'mountpoint': '/', 'filesystem': 'ext4'},
            ],
            'security_controls': controls,
            'local_accounts': [
                {'username': 'alice', 'uid': 1000, 'system_account': False},
            ],
        }
        for component, data in components.items():
            Event.objects.create(
                index='host_security_posture',
                host='test-host',
                source='host_security_posture',
                sourcetype='json',
                data=json.dumps({
                    'type': 'host_security_posture',
                    'event_type': 'posture_snapshot',
                    'component': component,
                    'data': data,
                }),
            )
        Event.objects.create(
            index='host_security_posture',
            host='test-host',
            source='host_security_posture',
            sourcetype='json',
            data=json.dumps({
                'type': 'host_security_posture',
                'event_type': 'posture_changed',
                'component': 'security_controls',
                'data': controls,
                'previous': {
                    **controls,
                    'secure_boot': {'state': 'available', 'enabled': False},
                },
            }),
        )
        Event.objects.create(
            index='host_security_posture',
            host='test-host',
            source='host_security_posture',
            sourcetype='json',
            data=json.dumps({
                'type': 'host_security_posture',
                'event_type': 'collection_status',
                'component': 'collector',
                'data': {
                    'state': 'ok',
                    'components_collected': sorted(components),
                    'components_failed': [],
                    'issues': [],
                    'collection_duration_ms': 15.0,
                },
            }),
        )

        call_command('seed_default_content', owner=DEV_SUPERUSER_USERNAME)
        request = SimpleNamespace(user=self.owner)
        posture_searches = SavedSearch.objects.filter(
            owner=self.owner,
            name__in={
                panel.search.removeprefix('run_saved_search ').strip('"')
                for dashboard in Dashboard.objects.filter(
                    created_by=self.owner,
                    name__in=self.POSTURE_DASHBOARDS,
                )
                for panel in dashboard.panels.all()
            },
        )

        self.assertEqual(posture_searches.count(), 13)
        for saved_search in posture_searches:
            result = run_pipeline(None, saved_search.query, request=request)
            rows = coerce_to_list_of_dicts(result)
            self.assertIsInstance(rows, list, saved_search.name)

    def test_seed_is_idempotent(self):
        call_command('seed_default_content', owner=DEV_SUPERUSER_USERNAME)
        search_count = SavedSearch.objects.filter(owner=self.owner).count()
        dashboard_count = Dashboard.objects.filter(created_by=self.owner).count()
        panel_count = Panel.objects.filter(dashboard__created_by=self.owner).count()

        call_command('seed_default_content', owner=DEV_SUPERUSER_USERNAME)

        self.assertEqual(SavedSearch.objects.filter(owner=self.owner).count(), search_count)
        self.assertEqual(Dashboard.objects.filter(created_by=self.owner).count(), dashboard_count)
        self.assertEqual(Panel.objects.filter(dashboard__created_by=self.owner).count(), panel_count)

    def test_seed_does_not_overwrite_edited_defaults(self):
        call_command('seed_default_content', owner=DEV_SUPERUSER_USERNAME)
        search = SavedSearch.objects.filter(owner=self.owner).first()
        search.query = 'search --limit=1'
        search.save(update_fields=['query'])

        call_command('seed_default_content', owner=DEV_SUPERUSER_USERNAME)

        search.refresh_from_db()
        self.assertEqual(search.query, 'search --limit=1')

    def test_seed_requires_existing_owner(self):
        with self.assertRaises(CommandError):
            call_command('seed_default_content', owner='no-such-user')


class UserRegistrationTests(TestCase):
    """
    Tests for removed self-registration routes.
    """

    def test_register_route_name_is_removed(self):
        with self.assertRaises(NoReverseMatch):
            reverse('register')

    def test_register_path_returns_404(self):
        response = self.client.get('/register/')
        self.assertEqual(response.status_code, 404)


class DefaultPermissionTests(TestCase):
    def test_new_user_gets_registered_group_and_expected_permissions(self):
        User = get_user_model()
        user = User.objects.create_user(username='permuser', password='testpass')

        self.assertTrue(user.groups.filter(name='Registered User').exists())
        self.assertSetEqual(
            user.get_all_permissions(),
            {
                'events.view_event',
                'dashboarding.view_dashboard',
                'dashboarding.view_panel',
                'crawlers.view_finding',
                'search2.view_savedsearch',
            },
        )

        group = user.groups.get(name="Registered User")
        permission_keys = set(
            group.permissions.values_list(
                "content_type__app_label",
                "content_type__model",
                "codename",
            )
        )
        self.assertSetEqual(
            permission_keys,
            {
                ("events", "event", "view_event"),
                ("dashboarding", "dashboard", "view_dashboard"),
                ("dashboarding", "panel", "view_panel"),
                ("crawlers", "finding", "view_finding"),
                ("search2", "savedsearch", "view_savedsearch"),
            },
        )


class UserProfileTests(TestCase):
    """
    Tests for user profile management.
    """

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='profileuser', password='testpass')

    def test_profile_view_requires_login(self):
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 302)

    def test_profile_view_post(self):
        self.client.login(username='profileuser', password='testpass')
        response = self.client.post(
            reverse('profile'),
            {
                'bio': 'Hello world!',
                'theme_preference': 'light',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.bio, 'Hello world!')


class LoginLogoutTests(TestCase):
    """
    Tests for login and logout functionality.
    """

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='loginuser', password='testpass')

    def test_login(self):
        response = self.client.post(reverse('login'), {'username': 'loginuser', 'password': 'testpass'})
        self.assertEqual(response.status_code, 302)

    def test_logout(self):
        self.client.login(username='loginuser', password='testpass')
        response = self.client.post(reverse('logout'))
        self.assertEqual(response.status_code, 302)
