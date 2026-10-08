---
title: Changelog
---

# Changelog

## Unreleased

- Changed agent plugin restarts to retry forever by default, with an
  exponential backoff (`restart_backoff`, `restart_backoff_max`) and a reset
  after a stable run (`restart_reset_after`). Before, a plugin that failed 3
  times in a row stopped for good, so a source outage of more than a few
  seconds silently ended collection until the agent restarted. `restart`
  now also accepts `True` and `False`, like crawler configuration.
- Added `plugins_alive` to each plugin entry in the agent heartbeat. The
  existing `alive` count includes the sender process, which hid a dead
  collector.
- Fixed the `kube_logs` plugin stalling forever when a container restarted
  and Kubernetes no longer had the previous container's logs. It now emits a
  `partial` collection status that records the gap and continues with the
  current container.
- Made summary date detection configurable through
  `SIEMATIC_SEARCH["SUMMARY_DATE_FORMATS"]`.
- Published the initial public alpha of SIEMatic. This release is early and
  may change without notice; production reliance requires a paid support
  contract (`sales@mcindi.com`).

- Reorganized project documentation into overview, quickstart, operations,
  search and dashboard, developer, reference, history, and changelog sections.
- Added generated search-command, REST API, and scoped Python API references.
- Added CI validation for strict documentation builds and environment-variable
  reference drift.
- Corrected documentation for cross-database joins, saved-search export/import,
  the `dashboarding/` module, Docker Compose commands, and shared container
  health checks.

Release-specific entries will be added when versioned releases are published.
