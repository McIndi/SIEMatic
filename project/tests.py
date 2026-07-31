"""
Tests for the project app.

This module contains unit tests for profiles, authentication, and default permissions.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.forms.models import model_to_dict
from django.test import TestCase, Client
from django.urls import NoReverseMatch, reverse

from project.management.commands.rundev import (
    Command as RundevCommand,
    DEV_SUPERUSER_USERNAME,
)

from .models import UserProfile


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
