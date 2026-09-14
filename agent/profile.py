"""Load one deployment-owned agent profile."""

import json
from pathlib import Path


def _required(environ, name):
    value = environ.get(name)
    if not value:
        raise ValueError(f'{name} must be set for this profile')
    return value


def _field(profile, name):
    if name not in profile:
        raise ValueError(f'{name} is required in the profile')
    return profile[name]


def _load_json(path):
    try:
        with Path(path).open(encoding='utf-8') as profile_file:
            return json.load(profile_file)
    except FileNotFoundError as exc:
        raise ValueError(f'profile file is missing: {path}') from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f'profile JSON is invalid: {path}') from exc


def _indexer_credentials(environ):
    return {
        'username': _required(environ, 'INDEXER_USERNAME'),
        'password': _required(environ, 'INDEXER_PASSWORD'),
    }


def _kube_logs(profile, environ):
    targets = _field(profile, 'targets')
    if not isinstance(targets, list) or not targets:
        raise ValueError('targets must be a non-empty list')

    normalized_targets = []
    target_ids = set()
    target_fields = ('namespace', 'container', 'index', 'source', 'sourcetype')
    for target in targets:
        if not isinstance(target, dict):
            raise ValueError('target must be an object')
        for name in target_fields:
            _field(target, name)
        if 'deployment' not in target and 'selector' not in target:
            raise ValueError('deployment or selector is required in each target')
        target_id = (
            target.get('namespace'),
            target.get('deployment'),
            target.get('selector'),
            target.get('container'),
        )
        if target_id in target_ids:
            raise ValueError('duplicate target id')
        target_ids.add(target_id)
        normalized_targets.append(dict(target))

    return {
        'name': 'kube_logs',
        'enabled': True,
        'poll_interval': _field(profile, 'poll_interval'),
        'targets': normalized_targets,
        'indexer_credentials': _indexer_credentials(environ),
    }


def _keycloak_events(profile, environ):
    keycloak = {
        'base_url': _required(environ, 'KEYCLOAK_BASE_URL'),
        'client_id': _required(environ, 'KEYCLOAK_CLIENT_ID'),
        'client_secret': _required(environ, 'KEYCLOAK_CLIENT_SECRET'),
        'token_realm': _required(environ, 'KEYCLOAK_TOKEN_REALM'),
        'ca_bundle': environ.get('KEYCLOAK_CA_BUNDLE') or None,
    }
    return {
        'name': 'keycloak_events',
        'enabled': True,
        'poll_interval': _field(profile, 'poll_interval'),
        'realm': _field(profile, 'realm'),
        'index': _field(profile, 'index'),
        'source': _field(profile, 'source'),
        'host': _field(profile, 'host'),
        'keycloak': keycloak,
        'indexer_credentials': _indexer_credentials(environ),
    }


def load_profile(path, environ):
    """Load and validate exactly one plugin profile."""
    profile = _load_json(path)
    if not isinstance(profile, dict):
        raise ValueError('profile must be an object')
    if 'plugins' in profile:
        raise ValueError('profile must define exactly one plugin')
    if _field(profile, 'version') != 1:
        raise ValueError('version must be 1')
    plugin = _field(profile, 'plugin')
    loaders = {
        'kube_logs': _kube_logs,
        'keycloak_events': _keycloak_events,
    }
    if plugin not in loaders:
        raise ValueError(f'unknown plugin: {plugin}')
    return [loaders[plugin](profile, environ)]
