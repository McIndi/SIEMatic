"""
Keycloak authentication for SIEMatic.

Signing in through an identity provider is only half the job. SIEMatic's
authorization is Django groups and model permissions, so the realm roles that
arrive with a login have to be turned into group membership on every sign-in.
That mapping lives here.
"""

import base64
import binascii
import json
import logging

from django.conf import settings
from django.contrib.auth.models import Group
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

logger = logging.getLogger(__name__)


def decode_jwt_payload(token):
    """
    Read the claims out of a JWT without verifying its signature.

    The only caller passes an access token that this process just received
    from the provider's token endpoint over TLS, so the transport is what
    establishes trust. Do not use this on a token that arrived from a client.

    Args:
        token: The encoded JWT, or None.

    Returns:
        dict: The payload claims, or an empty dict when it cannot be read.
    """
    if not token:
        return {}
    parts = token.split('.')
    if len(parts) != 3:
        return {}
    payload = parts[1]
    payload += '=' * (-len(payload) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload))
    except (binascii.Error, UnicodeDecodeError, ValueError) as error:
        logger.warning('Could not read access token claims: %s', error)
        return {}


def claim_at_path(claims, path):
    """
    Follow a dotted path into a claims dictionary.

    Keycloak nests realm roles at ``realm_access.roles``, and other providers
    nest them somewhere else, so the location is a setting rather than a
    constant.

    Args:
        claims: The claims dictionary.
        path: Dotted path, for example 'realm_access.roles'.

    Returns:
        The value at that path, or None when any step is missing.
    """
    value = claims
    for key in path.split('.'):
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


class SIEMaticOIDCBackend(OIDCAuthenticationBackend):
    """
    Authenticate against an OpenID Connect provider and map roles to groups.

    Group membership is rewritten from the provider's claims on every login,
    so revoking a role in the realm takes effect the next time that person
    signs in rather than needing a second change in SIEMatic.
    """

    def get_userinfo(self, access_token, id_token, payload):
        """
        Collect claims from the userinfo endpoint and the access token.

        Keycloak puts realm roles in the access token and not in the userinfo
        response, so a backend that reads only userinfo sees no roles at all
        and every user lands with no groups. Merging the two means the role
        mapping works against a stock realm, with no protocol mapper to
        configure.

        Args:
            access_token: The access token returned by the provider.
            id_token: The ID token returned by the provider.
            payload: The full token endpoint response.

        Returns:
            dict: Claims from userinfo, with access token claims filling gaps.
        """
        userinfo = super().get_userinfo(access_token, id_token, payload)
        merged = dict(decode_jwt_payload(access_token))
        # Userinfo wins on any key both carry; it is the endpoint whose
        # contents the provider intends for the client to consume.
        merged.update(userinfo or {})
        return merged

    def get_username(self, claims):
        """
        Use the provider's username so the two systems name people the same.

        The library's default is a hash of the email address, which makes
        SIEMatic's audit trail impossible to line up against the provider's
        own login events.

        Args:
            claims: The claims for the user signing in.

        Returns:
            str: The username to store.
        """
        username = claims.get('preferred_username')
        if username:
            return username
        return super().get_username(claims)

    def filter_users_by_claims(self, claims):
        """
        Find the existing account for these claims, by username then email.

        This makes the provider's ``preferred_username`` the identity that
        SIEMatic keys on, so whoever administers the realm decides which local
        account a login lands on.

        Args:
            claims: The claims for the user signing in.

        Returns:
            QuerySet: Matching users, empty when this is a first login.
        """
        username = claims.get('preferred_username')
        if username:
            matches = self.UserModel.objects.filter(username__iexact=username)
            if matches.exists():
                return matches
        return super().filter_users_by_claims(claims)

    def roles_from_claims(self, claims):
        """
        Read the provider roles out of the claims.

        Args:
            claims: The claims for the user signing in.

        Returns:
            list: Role names, empty when the claim is absent or malformed.
        """
        path = getattr(settings, 'OIDC_GROUP_CLAIM', 'realm_access.roles')
        roles = claim_at_path(claims, path)
        if isinstance(roles, str):
            return [roles]
        if not isinstance(roles, (list, tuple)):
            return []
        return [role for role in roles if isinstance(role, str)]

    def sync_user(self, user, claims):
        """
        Rewrite groups, flags, and name from the provider's claims.

        Group membership is set rather than added. The project adds every new
        user to 'Registered User' with a post_save signal, which fires while
        the account is being created and before any claim has been read, so an
        additive mapping would leave that membership in place whatever the
        realm says. Setting makes the provider authoritative.

        Args:
            user: The user to update.
            claims: The claims for this login.

        Returns:
            The updated user, saved.
        """
        roles = self.roles_from_claims(claims)
        group_map = getattr(settings, 'OIDC_GROUP_MAP', {})
        wanted = set()
        for role in roles:
            wanted.update(group_map.get(role, []))

        groups = list(Group.objects.filter(name__in=wanted))
        found = {group.name for group in groups}
        missing = wanted - found
        if missing:
            logger.warning(
                'OIDC_GROUP_MAP names groups that do not exist: %s',
                ', '.join(sorted(missing)),
            )
        user.groups.set(groups)

        staff_roles = set(getattr(settings, 'OIDC_STAFF_ROLES', []))
        superuser_roles = set(getattr(settings, 'OIDC_SUPERUSER_ROLES', []))
        held = set(roles)
        user.is_superuser = bool(held & superuser_roles)
        # A superuser that cannot reach the admin is not much of one.
        user.is_staff = user.is_superuser or bool(held & staff_roles)

        user.email = claims.get('email', user.email) or ''
        user.first_name = claims.get('given_name', user.first_name) or ''
        user.last_name = claims.get('family_name', user.last_name) or ''
        user.save()

        logger.info(
            'Mapped %s roles %s to groups %s',
            user.username,
            sorted(held) or 'none',
            sorted(found) or 'none',
        )
        return user

    def create_user(self, claims):
        """
        Create an account on first login and apply the claim mapping.

        Args:
            claims: The claims for this login.

        Returns:
            The new user.
        """
        user = super().create_user(claims)
        return self.sync_user(user, claims)

    def update_user(self, user, claims):
        """
        Refresh an existing account from the claims on this login.

        Args:
            user: The matched user.
            claims: The claims for this login.

        Returns:
            The updated user.
        """
        return self.sync_user(user, claims)
