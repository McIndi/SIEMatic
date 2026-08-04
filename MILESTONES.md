# Milestones

Each milestone after M0 is a tracer round through business logic, interface,
data, packaging, automation, tests, docs, and security. A milestone is reached
only when all eight lanes are `OK` in `PROJECT_STATUS.md`.

## M0 - Walking Skeleton

Goal: connect all eight lanes with the smallest real, releasable system.

- [ ] The system installs and exposes a documented version and help path.
- [ ] CI builds and publishes a versioned `0.0.x` artifact.
- [x] A smoke-capable automated test suite runs in CI.
- [x] A README exists.
- [x] The storage location and backup-and-restore procedure are documented.
- [ ] The security floor is complete:
  - [x] Application secrets load from environment variables.
  - [ ] Runtime dependencies are fully pinned.
  - [x] CI runs a dependency-vulnerability scan.
  - [x] Transport and TLS assumptions are documented.
  - [x] `SECURITY.md` contains a reporting path and initial threat-model note.

The configurable summary date-format change is a completed targeted tracer
bullet. It improves a real search path with tests and documentation, but it does
not clear the packaging, automation, or security gaps in M0.

## Proposed M1 - Portable saved searches

Goal: export and import one versioned saved search through a documented,
permission-checked interface.

Why this slice: it retires format and ownership risks before dashboard packs or
larger content bundles depend on them.

| Lane | Target state at this milestone |
|------|--------------------------------|
| Business logic | Validate a versioned saved-search document and conflict policy. |
| Interface | Provide authenticated export and import operations. |
| Data | Preserve ownership and sharing semantics without direct database edits. |
| Packaging | Include the format and implementation in the published artifact. |
| Automation | Exercise an export/import round trip in CI. |
| Tests | Cover validation, conflicts, permissions, and round trips. |
| Docs | Publish a how-to, format reference, and changelog entry. |
| Security | Reject unauthorized imports and bound document size and complexity. |

## Proposed M2 - Operational metrics baseline

Goal: expose bounded application and crawler metrics with a documented scrape
and alerting path.

Why this slice: operators currently cannot measure health without building a
custom integration, which limits safe deployment feedback.

| Lane | Target state at this milestone |
|------|--------------------------------|
| Business logic | Record request, ingestion, crawler, and failure counters. |
| Interface | Expose an authenticated or network-restricted metrics endpoint. |
| Data | Define metric lifetime and cardinality limits. |
| Packaging | Include the metrics dependency and configuration in the artifact. |
| Automation | Add a scrape-health check and example monitoring configuration. |
| Tests | Verify values, access controls, and cardinality protections. |
| Docs | Add setup, metric reference, and troubleshooting guidance. |
| Security | Prevent secret or tenant data leakage through labels and samples. |

## Proposed M3 - Database-backed alert subscriptions

Goal: let users manage scoped rule and severity subscriptions through the
application.

Why this slice: it replaces operator-only crawler configuration with an
auditable user workflow and establishes the configuration ownership model.

| Lane | Target state at this milestone |
|------|--------------------------------|
| Business logic | Resolve subscriptions by rule, severity, user, and enabled state. |
| Interface | Provide permission-checked web and REST management. |
| Data | Add a migration, constraints, and deletion behavior. |
| Packaging | Ship the migration in the versioned artifact. |
| Automation | Apply and validate the migration in CI and deployment checks. |
| Tests | Cover matching, deduplication, authorization, and migration behavior. |
| Docs | Add user, operator, API, and upgrade guidance. |
| Security | Enforce ownership and prevent recipient enumeration or alert abuse. |
