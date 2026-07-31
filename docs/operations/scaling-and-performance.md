---
title: Scaling and Performance
---

# Scaling and Performance

Start with one PostgreSQL database and measure ingestion rate, query latency,
crawler duration, memory, and database growth before adding capacity.

## Database

SQLite is suitable for `rundev`. Use PostgreSQL for concurrent production
workloads. The frequently filtered event metadata fields and timestamps already
have ordinary database indexes. For large append-heavy PostgreSQL tables, test
a BRIN index on `created` against representative data:

```sql
CREATE INDEX CONCURRENTLY idx_events_created_brin
ON events_event USING brin (created);
```

Review query plans before and after adding it. Maintain backups and routine
PostgreSQL vacuum/analyze operations.

SIEMatic can query configured Django database aliases, and the `join` command
can combine data from another alias with pandas. Cross-database joins move data
into process memory and can be CPU- and memory-intensive. Filter and limit both
sides before joining.

## Search

The default `SIEMATIC_SEARCH["MAX_ROWS"]` cap is 10,000 rows. Prefer selective
filters, projected fields, and early `head` or `search --limit` stages. Commands
that convert QuerySets to DataFrames trade database pushdown for flexibility.
Monitor these commands carefully on large datasets.

## Services

Role-specific settings allow web, agent, indexer, and crawler processes to run
on different machines. Scale only after identifying the constrained role.

Crawler instances are configuration-driven but are not coordinated by a shared
job-claiming system. If the same instance runs on multiple nodes, it can process
the same events or retention range more than once. Partition instances by
database alias or rule and avoid duplicate schedules.

Tune the CherryPy host, port, thread, request, and timeout settings through the
documented environment variables. External caching, task queues, reverse
proxies, and load balancers are deployment integrations. They are not bundled
SIEMatic services. Test them with your own workload and failure tests.
