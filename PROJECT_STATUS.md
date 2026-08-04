<!-- MILEMARKER: milestone=M0 lanes_ok=6/8 lag=1 updated=2026-08-04 -->
# Project Status

This is an initial, evidence-based assessment. The inferred statuses need owner
confirmation. Status tokens are `OK`, `WIP`, `TODO`, `LAG`, and `N/A`. A lane is
`LAG` when it is behind the current milestone.

**Current milestone:** M0 - Walking Skeleton (not yet cleared)

## Lane status

| # | Lane | Status | Next action |
|---|------|--------|-------------|
| 1 | Business logic | OK | Confirm the supported alpha feature boundary. |
| 2 | Interface | OK | Keep the web, REST, and command references synchronized with changes. |
| 3 | Data | OK | Automate and exercise the documented database restore procedure. |
| 4 | Packaging | LAG | Define a version and publish a pinned, reproducible artifact from CI. |
| 5 | Automation | WIP | Add release automation and a tested restore job. |
| 6 | Tests | OK | Keep the full Django suite and coverage report as CI gates. |
| 7 | Docs | OK | Add release-specific changelog entries as versions are published. |
| 8 | Security | OK | Add secret scanning, an SBOM, and artifact signing as hardening beyond the M0 floor. |

## Evidence summary

- Business logic and interface: the Django applications expose collection,
  indexing, search, dashboards, findings, alerts, web views, and REST APIs.
- Data: Django models and migrations exist. PostgreSQL and SQLite storage and a
  manual backup-and-restore procedure are documented.
- Packaging and automation: a Dockerfile, Compose configuration, and GitHub CI
  builds exist. No versioned publish, SBOM, provenance, signing, or automated
  restore evidence was found.
- Tests: 116 tests pass locally, and CI runs tests with coverage on Python 3.13
  and 3.14.
- Docs: MkDocs navigation, operations guides, generated references, a README,
  and a changelog exist and build in strict mode.
- Security: authentication, model permissions, environment-loaded secrets, and
  TLS settings exist. `SECURITY.md`, a CI `pip-audit` dependency-vulnerability
  scan, and fully pinned runtime and docs dependencies close the M0 security
  floor. Secret scan, SAST, SBOM, and artifact-signing configuration remain
  open as post-M0 hardening.

## Ripple audit for the summary date-format tracer bullet

| Lane | Effect |
|---|---|
| Business logic | Added validated, configurable summary date formats. |
| Interface | Added `SIEMATIC_SEARCH["SUMMARY_DATE_FORMATS"]`; no endpoint or schema changed. |
| Data | No model, stored-data, or migration change. |
| Packaging | No artifact change. |
| Automation | Existing CI commands cover the change. |
| Tests | Added default, custom, numeric-regression, and invalid-config cases. |
| Docs | Updated the search guide, limitation list, and changelog. |
| Security | No new external input or privilege boundary; malformed settings fall back safely. |

## Ripple audit for the SECURITY.md and dependency-scan tracer bullet

| Lane | Effect |
|---|---|
| Business logic | No behavior change. |
| Interface | No endpoint or schema changed. |
| Data | No model, stored-data, or migration change. |
| Packaging | No artifact change; dependency pinning remains open. |
| Automation | Added a `dependency-scan` CI job running `pip-audit` against `requirements.txt` and `requirements-docs.txt`. |
| Tests | No test-suite change; `pip-audit` ran clean locally against both requirement files before landing the CI job. |
| Docs | No doc-site change; `SECURITY.md` added at the repository root. |
| Security | Added `SECURITY.md` with a reporting path and threat-model note, and an automated dependency-vulnerability scan gating CI. Runtime dependency pinning is still open. |

## Ripple audit for the dependency-pinning tracer bullet

| Lane | Effect |
|---|---|
| Business logic | No behavior change. |
| Interface | No endpoint or schema changed. |
| Data | No model, stored-data, or migration change. |
| Packaging | No artifact change; versioned, published artifact remains open. |
| Automation | Existing CI install and dependency-scan steps consume the pinned files unchanged. |
| Tests | Full local suite (122 tests) re-run against the pinned dependency set; no regressions. |
| Docs | No doc-site content change; `mkdocs build --strict` re-verified against the pinned docs dependencies. |
| Security | `requirements.txt` and `requirements-docs.txt` now pin exact versions for every direct and transitive dependency, closing the last open M0 security-floor item. While upgrading, a newly released `mkdocs-gen-files==0.6.1` and `mkdocs-literate-nav==0.6.3` were found to add a dependency on a package called `properdocs` that overwrites `sys.modules["mkdocs"]` to redirect all `mkdocs.*` imports to itself and prints messaging urging migration off MkDocs. This was treated as a supply-chain risk and avoided: those two packages are pinned to their prior versions (`0.6.0` / `0.6.2`), which depend only on `mkdocs` and were confirmed clean. Every other dependency is pinned at its current latest release. |

## The ripple rule

A business-logic change can push interface, data, tests, docs, or security to
`LAG`. Review all eight lanes before marking an increment complete. A milestone
is reached only when every lane is `OK`.

## Cross-project rollup convention

Keep the first-line marker and the lane table stable. From a directory that
contains multiple projects, run:

```bash
grep -r "^<!-- MILEMARKER:" --include=PROJECT_STATUS.md .
```
