"""
Tests for the project app.

This module contains unit tests for profiles, authentication, and default permissions.
"""
from django.forms.models import model_to_dict
from django.test import TestCase, Client
from django.urls import NoReverseMatch, reverse
from django.contrib.auth import get_user_model
from .models import UserProfile

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
