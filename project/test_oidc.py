"""
Tests for Keycloak authentication and the role to group mapping.
"""

import base64
import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings

from project.oidc import SIEMaticOIDCBackend, claim_at_path, decode_jwt_payload
from project.signals import AGENT_GROUP_NAME, REGISTERED_GROUP_NAME


def fake_access_token(claims):
    """Build a JWT-shaped string whose payload holds these claims."""

    def segment(data):
        raw = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
        return raw.rstrip('=')

    return f"{segment({'alg': 'RS256'})}.{segment(claims)}.signature"


class DecodeJwtPayloadTests(TestCase):
    def test_it_reads_claims_from_a_well_formed_token(self):
        token = fake_access_token({'realm_access': {'roles': ['rossoctl-admin']}})

        self.assertEqual(
            decode_jwt_payload(token),
            {'realm_access': {'roles': ['rossoctl-admin']}},
        )

    def test_it_returns_nothing_for_junk(self):
        for value in (None, '', 'not-a-jwt', 'a.b', 'a.!!!.c'):
            self.assertEqual(decode_jwt_payload(value), {})


class ClaimPathTests(TestCase):
    def test_it_walks_a_nested_path(self):
        claims = {'realm_access': {'roles': ['viewer']}}

        self.assertEqual(claim_at_path(claims, 'realm_access.roles'), ['viewer'])

    def test_a_missing_step_is_not_an_error(self):
        self.assertIsNone(claim_at_path({}, 'realm_access.roles'))
        self.assertIsNone(claim_at_path({'realm_access': 'wrong type'}, 'realm_access.roles'))


@override_settings(
    OIDC_GROUP_CLAIM='realm_access.roles',
    OIDC_GROUP_MAP={
        'rossoctl-admin': [REGISTERED_GROUP_NAME],
        'rossoctl-viewer': [REGISTERED_GROUP_NAME],
    },
    OIDC_STAFF_ROLES=[],
    OIDC_SUPERUSER_ROLES=[],
)
class GroupMappingTests(TestCase):
    def setUp(self):
        self.backend = SIEMaticOIDCBackend.__new__(SIEMaticOIDCBackend)
        self.backend.UserModel = get_user_model()
        Group.objects.get_or_create(name=REGISTERED_GROUP_NAME)
        Group.objects.get_or_create(name=AGENT_GROUP_NAME)

    def make_user(self, username='presenter'):
        return get_user_model().objects.create_user(username=username)

    def test_a_mapped_role_grants_its_group(self):
        user = self.make_user()

        self.backend.sync_user(
            user, {'realm_access': {'roles': ['rossoctl-admin']}}
        )

        self.assertEqual(
            list(user.groups.values_list('name', flat=True)), [REGISTERED_GROUP_NAME]
        )

    def test_group_membership_is_replaced_not_added_to(self):
        # The post_save signal puts every new user in Registered User before a
        # single claim has been read. An additive mapping would leave that in
        # place no matter what the realm says.
        user = self.make_user()
        self.assertIn(
            REGISTERED_GROUP_NAME, list(user.groups.values_list('name', flat=True))
        )

        self.backend.sync_user(user, {'realm_access': {'roles': ['unmapped-role']}})

        self.assertEqual(list(user.groups.values_list('name', flat=True)), [])

    def test_no_realm_role_grants_the_agent_group(self):
        user = self.make_user()

        self.backend.sync_user(
            user,
            {'realm_access': {'roles': ['rossoctl-admin', 'rossoctl-viewer', 'Agent']}},
        )

        self.assertNotIn(
            AGENT_GROUP_NAME, list(user.groups.values_list('name', flat=True))
        )

    def test_a_missing_roles_claim_leaves_no_groups(self):
        user = self.make_user()

        self.backend.sync_user(user, {'email': 'nobody@example.test'})

        self.assertEqual(list(user.groups.values_list('name', flat=True)), [])

    def test_a_group_named_in_the_map_but_absent_is_skipped(self):
        user = self.make_user()

        with override_settings(OIDC_GROUP_MAP={'rossoctl-admin': ['No Such Group']}):
            self.backend.sync_user(
                user, {'realm_access': {'roles': ['rossoctl-admin']}}
            )

        self.assertEqual(list(user.groups.values_list('name', flat=True)), [])

    def test_admin_flags_stay_off_by_default(self):
        user = self.backend.sync_user(
            self.make_user(), {'realm_access': {'roles': ['rossoctl-admin']}}
        )

        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    @override_settings(OIDC_SUPERUSER_ROLES=['realm-admin'])
    def test_a_superuser_role_also_grants_staff(self):
        user = self.backend.sync_user(
            self.make_user(), {'realm_access': {'roles': ['realm-admin']}}
        )

        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)

    @override_settings(OIDC_STAFF_ROLES=['siematic-staff'])
    def test_losing_a_role_revokes_the_flag_on_next_login(self):
        user = self.make_user()
        self.backend.sync_user(user, {'realm_access': {'roles': ['siematic-staff']}})
        self.assertTrue(user.is_staff)

        self.backend.sync_user(user, {'realm_access': {'roles': []}})

        self.assertFalse(user.is_staff)

    def test_it_copies_the_name_and_email(self):
        user = self.backend.sync_user(
            self.make_user(),
            {
                'realm_access': {'roles': []},
                'email': 'lee@example.test',
                'given_name': 'Lee',
                'family_name': 'Ortiz',
            },
        )

        self.assertEqual(user.email, 'lee@example.test')
        self.assertEqual(user.first_name, 'Lee')
        self.assertEqual(user.last_name, 'Ortiz')


class UsernameTests(TestCase):
    def setUp(self):
        self.backend = SIEMaticOIDCBackend.__new__(SIEMaticOIDCBackend)
        self.backend.UserModel = get_user_model()

    def test_the_provider_username_is_used_verbatim(self):
        self.assertEqual(
            self.backend.get_username({'preferred_username': 'presenter'}),
            'presenter',
        )

    def test_an_existing_account_is_matched_by_username(self):
        get_user_model().objects.create_user(username='presenter')

        matches = self.backend.filter_users_by_claims(
            {'preferred_username': 'Presenter', 'email': 'other@example.test'}
        )

        self.assertEqual([user.username for user in matches], ['presenter'])


class UserinfoMergeTests(TestCase):
    def test_access_token_claims_fill_in_what_userinfo_omits(self):
        # Keycloak returns realm roles in the access token and not from the
        # userinfo endpoint, so reading only userinfo yields no roles at all.
        backend = SIEMaticOIDCBackend.__new__(SIEMaticOIDCBackend)
        token = fake_access_token(
            {'realm_access': {'roles': ['rossoctl-admin']}, 'email': 'stale@example.test'}
        )

        with_userinfo = {'email': 'current@example.test', 'preferred_username': 'lee'}
        original = SIEMaticOIDCBackend.__mro__[1].get_userinfo
        try:
            SIEMaticOIDCBackend.__mro__[1].get_userinfo = (
                lambda self, a, i, p: with_userinfo
            )
            claims = backend.get_userinfo(token, None, {})
        finally:
            SIEMaticOIDCBackend.__mro__[1].get_userinfo = original

        self.assertEqual(claims['realm_access']['roles'], ['rossoctl-admin'])
        # Userinfo wins where both carry the same key.
        self.assertEqual(claims['email'], 'current@example.test')


class AuthenticationBackendSettingsTests(TestCase):
    def test_local_passwords_are_the_only_option_by_default(self):
        from django.conf import settings

        self.assertFalse(settings.OIDC_ENABLED)
        self.assertEqual(
            settings.AUTHENTICATION_BACKENDS,
            ['django.contrib.auth.backends.ModelBackend'],
        )
