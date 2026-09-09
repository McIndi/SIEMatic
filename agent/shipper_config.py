"""Deployment-specific configuration for the two OpenShift shippers."""


def _required(environ, name):
    value = environ.get(name)
    if not value:
        raise ValueError(f'{name} must be set for this shipper')
    return value


def plugins_for_role(role, environ):
    """Return the safe plugin configuration selected by one deployment role."""
    if role == 'kube_logs':
        return [{
            'name': 'kube_logs',
            'enabled': True,
            'poll_interval': 5,
            'targets': [
                {
                    'namespace': 'team1',
                    'deployment': 'weather-service',
                    'container': 'authbridge-proxy',
                    'index': 'authbridge',
                    'source': 'weather-service/authbridge-proxy',
                    'sourcetype': 'logfmt',
                },
                {
                    'namespace': 'team1',
                    'deployment': 'weather-tool',
                    'container': 'authbridge-proxy',
                    'index': 'authbridge',
                    'source': 'weather-tool/authbridge-proxy',
                    'sourcetype': 'logfmt',
                },
                {
                    'namespace': 'team1',
                    'deployment': 'reservation-agent',
                    'container': 'authbridge-proxy',
                    'index': 'authbridge',
                    'source': 'reservation-agent/authbridge-proxy',
                    'sourcetype': 'logfmt',
                },
                {
                    'namespace': 'team1',
                    'deployment': 'reservation-tool',
                    'container': 'authbridge-proxy',
                    'index': 'authbridge',
                    'source': 'reservation-tool/authbridge-proxy',
                    'sourcetype': 'logfmt',
                },
                {
                    'namespace': 'vault',
                    'selector': 'app.kubernetes.io/name=vault',
                    'container': 'vault',
                    'index': 'vault',
                    'source': 'vault/audit',
                    'sourcetype': 'json',
                    'vault_audit': True,
                },
            ],
        }]
    if role == 'keycloak_events':
        return [{
            'name': 'keycloak_events',
            'enabled': True,
            'poll_interval': 30,
            'realm': 'rossoctl',
            'index': 'keycloak',
            'source': 'keycloak/rossoctl',
            'host': 'keycloak',
            'keycloak': {
                'base_url': _required(environ, 'KEYCLOAK_BASE_URL'),
                'client_id': _required(environ, 'KEYCLOAK_CLIENT_ID'),
                'client_secret': _required(environ, 'KEYCLOAK_CLIENT_SECRET'),
                'token_realm': environ.get('KEYCLOAK_TOKEN_REALM', 'master'),
                'ca_bundle': environ.get('KEYCLOAK_CA_BUNDLE') or None,
            },
        }]
    raise ValueError(f'Unknown SIEMATIC_SHIPPER_ROLE: {role}')
