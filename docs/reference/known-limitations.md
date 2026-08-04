---
title: Known Limitations
---

# Known Limitations

## Search and analytics

- Saved searches do not support declared parameters, version history, or
  per-search export/import. `dumpdata` and `loaddata` operate on broader Django
  project data.
- Cross-database joins are implemented through pandas. Both inputs are
  materialized in application memory, so large joins can be slow and consume
  substantial CPU and memory.
- DataFrame conversions have the same memory constraint. JSON values must be
  stored with numeric types for numeric aggregation.
- Numeric mode can be absent when all values are unique, and text summaries
  show the three most common values.
- Dashboard sharing, versioned export/import, and packaged example dashboards or
  search packs are not provided.

## Deployment and tenancy

- SIEMatic does not include a worker-node inventory model or database-backed
  coordination for duplicate crawler instances. Operators must partition
  crawler work deliberately.
- Metrics are not bundled. Python logging is available, but operators must
  integrate their own metrics and monitoring stack.
- Object-level permissions through Django Guardian and multi-tenant isolation
  are not implemented. Model permissions and owner-scoped views must not be
  treated as a tenant security boundary.

## Alert subscriptions are configuration-based

Alert recipients and thresholds are configured through crawler settings.
SIEMatic does not provide a database-backed `AlertSubscription` model. It also
does not provide a general database-backed configuration table. Thus, users
cannot manage personal rule or severity subscriptions through the application.
