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
| `DJANGO_DEBUG` | `False` | Enables Django debug mode. Never enable in production. |
| `DJANGO_LOG_LEVEL` | `INFO` | Python and Django logging level. |
| `DJANGO_SECRET_KEY` | none (required) | Django signing secret; startup fails when absent or left at the placeholder. |
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
| `SIEMATIC_AGENT_SYSMON_ONLY` | `False` | Deprecated alias for `SIEMATIC_AGENT_CORE_ONLY`. |
| `SIEMATIC_AGENT_CORE_ONLY` | `False` | Uses the cross-platform Sysmon and network-security plugins instead of platform defaults. |
| `SIEMATIC_ANON_THROTTLE_RATE` | `20/hour` | DRF anonymous request throttle rate. |
| `SIEMATIC_INGEST_THROTTLE_RATE` | `20000/hour` | DRF event-ingestion throttle rate. |
| `SIEMATIC_SEARCH_THROTTLE_RATE` | `120/min` | DRF search throttle rate. |
| `SIEMATIC_TLS_ENABLED` | `False` | Enables HTTPS-oriented cookie, redirect, and HSTS settings. |
