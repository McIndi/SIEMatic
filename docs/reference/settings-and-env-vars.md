---
title: Settings and Environment Variables
---

# Settings and Environment Variables

These variables are read by modules under `SIEMatic/settings/`. Boolean values
accept `1`, `true`, `yes`, or `on` (case-insensitive); other values are false.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_ENGINE` | `django.db.backends.sqlite3` | Django database backend. Compose uses PostgreSQL. |
| `DATABASE_HOST` | empty | Database server hostname. |
| `DATABASE_NAME` | `db.sqlite3` | Database name or SQLite file path. |
| `DATABASE_PASSWORD` | empty | Database user's password. |
| `DATABASE_PORT` | empty | Database server port. |
| `DATABASE_USER` | empty | Database username. |
| `DEFAULT_FROM_EMAIL` | `siematic@example.com` | Sender address for application email. |
| `DJANGO_ALLOWED_HOSTS` | role-specific local hosts | Comma-separated hostnames accepted by Django. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | empty | Comma-separated `scheme://host` origins Django accepts unsafe requests from. Set this to the external URL when running behind an ingress or route. |
| `DJANGO_DEBUG` | `False` | Enables Django debug mode. Never enable in production. |
| `DJANGO_LOG_LEVEL` | `INFO` | Python and Django logging level. |
| `DJANGO_LOG_TO_FILE` | `True` | Writes logs to `logs/` in addition to stdout. Set false in containers, where the working directory may not be writable. |
| `DJANGO_SECRET_KEY` | none (required) | Django signing secret; startup fails when absent or left at the placeholder. |
| `DJANGO_TIME_ZONE` | `UTC` | Time zone used to render timestamps. Keep UTC when correlating with other systems. |
| `DJANGO_TRUST_PROXY_PROTO_HEADER` | `False` | Reads the request scheme from `X-Forwarded-Proto`. Only enable when a trusted proxy sets that header. |
| `EMAIL_BACKEND` | file-based backend | Django email backend import path. |
| `EMAIL_HOST` | `localhost` | SMTP server hostname. |
| `EMAIL_HOST_PASSWORD` | empty | SMTP password. |
| `EMAIL_HOST_USER` | empty | SMTP username. |
| `EMAIL_PORT` | `25` | SMTP server port. |
| `EMAIL_USE_SSL` | `False` | Connect to SMTP with implicit TLS. Mutually exclusive with `EMAIL_USE_TLS`. |
| `EMAIL_USE_TLS` | `False` | Upgrade the SMTP connection with STARTTLS. Mutually exclusive with `EMAIL_USE_SSL`. |
| `INDEXER_CA_BUNDLE` | empty | CA certificate bundle used by agents to verify the indexer. |
| `INDEXER_HOSTNAME` | `localhost` | Indexer hostname used by agent and indexer role settings. |
| `INDEXER_MODE` | unset | Selects the indexer's minimal URL configuration and disables the debug toolbar. |
| `INDEXER_PASSWORD` | none | Password used by an agent to authenticate to the indexer. |
| `INDEXER_PORT` | `8000` | Indexer port; Compose normally overrides this. |
| `INDEXER_SSL_CERT` | empty | Indexer TLS certificate path. |
| `INDEXER_SSL_KEY` | empty | Indexer TLS private-key path. |
| `INDEXER_TLS` | value of `SIEMATIC_TLS_ENABLED` | Enables TLS for agent-to-indexer transport. |
| `INDEXER_USERNAME` | none | Username used by an agent to authenticate to the indexer. |
| `OIDC_GROUP_CLAIM` | `realm_access.roles` | Dotted path to the roles claim. Keycloak nests realm roles here. |
| `OIDC_GROUP_MAP` | `{}` | JSON object mapping a provider role to the Django groups it grants, for example `{"rossoctl-admin": ["Registered User"]}`. Rewritten on every login. |
| `OIDC_ISSUER` | empty | Realm issuer URL, for example `https://keycloak.example/realms/rossoctl`. Setting it turns provider login on; leaving it empty keeps local passwords as the only option. |
| `OIDC_OP_AUTHORIZATION_ENDPOINT` | derived from `OIDC_ISSUER` | Override for a provider that does not use Keycloak's endpoint layout. |
| `OIDC_OP_JWKS_ENDPOINT` | derived from `OIDC_ISSUER` | Override for the signing key set. |
| `OIDC_OP_TOKEN_ENDPOINT` | derived from `OIDC_ISSUER` | Override for the token endpoint. |
| `OIDC_OP_USER_ENDPOINT` | derived from `OIDC_ISSUER` | Override for the userinfo endpoint. |
| `OIDC_PROVIDER_NAME` | `Keycloak` | Name shown on the login button. |
| `OIDC_RP_CLIENT_ID` | empty | Client ID registered in the realm. Required once `OIDC_ISSUER` is set. |
| `OIDC_RP_CLIENT_SECRET` | empty | Client secret for a confidential client. |
| `OIDC_RP_SCOPES` | `openid email profile` | Scopes requested at login. |
| `OIDC_RP_SIGN_ALGO` | `RS256` | Algorithm the provider signs tokens with. |
| `OIDC_STAFF_ROLES` | empty | Comma-separated roles granting Django admin access. Empty means no role does. |
| `OIDC_SUPERUSER_ROLES` | empty | Comma-separated roles granting superuser. Empty means no role does. |
| `SIEMATIC_AGENT_SYSMON_ONLY` | `False` | Deprecated alias for `SIEMATIC_AGENT_CORE_ONLY`. |
| `SIEMATIC_AGENT_CORE_ONLY` | `False` | Uses the cross-platform Sysmon, network-security, and host-security-posture plugins instead of platform defaults. |
| `SIEMATIC_ANON_THROTTLE_RATE` | `20/hour` | DRF anonymous request throttle rate. |
| `SIEMATIC_INGEST_THROTTLE_RATE` | `20000/hour` | DRF event-ingestion throttle rate. |
| `SIEMATIC_SEARCH_THROTTLE_RATE` | `120/min` | DRF search throttle rate. |
| `SIEMATIC_TLS_ENABLED` | `False` | Enables HTTPS-oriented cookie, redirect, and HSTS settings. |

## Python settings

`SIEMATIC_SEARCH["SUMMARY_DATE_FORMATS"]` is an ordered list of Python
`strptime` formats used to identify date columns in search-result summaries.
Its defaults are `%Y-%m-%d`, `%Y-%m-%d %H:%M:%S`, `%m/%d/%Y`, and `%d/%m/%Y`.
Add or replace entries in the Django settings module when result data uses a
different date representation.
