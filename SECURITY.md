# Security Policy

SIEMatic is early-release alpha software (see [README](README.md)). Report
issues promptly so they can be triaged against that status.

## Reporting a vulnerability

Email **security@mcindi.com** with a description of the issue, the affected
version or commit, and reproduction steps. Do not open a public GitHub issue
for a suspected vulnerability. Expect an acknowledgment within 5 business
days. We'll coordinate a fix and disclosure timeline with you before any
public write-up.

## Supported versions

SIEMatic has not yet published a versioned release (see `PROJECT_STATUS.md`,
milestone M0). Until a `1.0` line exists, only the `main` branch is
supported; fixes land there first.

## Threat model note

SIEMatic ingests and indexes security events from agents and crawlers, then
exposes them through a Django web UI and REST API. The main trust boundaries
today:

- **Agent and indexer connections** authenticate over WebSocket with
  credentials tied to a dedicated account in the `Agent` group
  (`docs/operations/deploying.md`). A compromised agent credential can write
  events but is scoped by that account's group permissions, not full admin
  access.
- **Transport** is expected to run over TLS end-to-end or behind a
  TLS-terminating reverse proxy; `SIEMATIC_TLS_ENABLED` and
  `DJANGO_ALLOWED_HOSTS` must match the deployment topology, or the app
  should be treated as unsafe for anything but local development.
- **Secrets** (`DJANGO_SECRET_KEY`, database and indexer credentials) load
  from environment variables via `.env`, never from source. A leaked `.env`
  or database backup is equivalent to full application compromise and should
  be treated as an incident, not just a rotation.
- **Ingested event data is untrusted input.** Search queries and crawler
  output are user- or agent-supplied and pass through the pipeline search
  language and indexer before display; injection into stored queries or
  rendered dashboards is the main class of concern we watch for in review.
- **Not yet covered:** automated dependency-vulnerability scanning, secret
  scanning, SAST, SBOM generation, and artifact signing are tracked as open
  gaps in `PROJECT_STATUS.md` and `MILESTONES.md` rather than assumed to be
  handled elsewhere.

This note will be revisited as the ingestion surface, authentication model,
or deployment topology changes materially, not on a fixed schedule.
