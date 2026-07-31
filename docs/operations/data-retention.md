---
title: Data Retention
---

# Data Retention

`DataRetentionCrawler` deletes events older than a configured number of days.
Treat retention changes as destructive operations. Before you enable a policy,
make sure that its backups, filters, and database aliases are correct.

## Configure a policy

Each policy is a scheduled crawler instance whose `name` is
`data_retention_crawler`:

```python
"30_day_retention_crawler": {
    "name": "data_retention_crawler",
    "enabled": True,
    "type": "scheduled",
    "schedule": "0 2 * * *",
    "retention_days": 30,
    "db_alias": "default",
    "rules": [
        {
            "split_by": "index",
            "allow": ["default", "sysmon", "security"],
            "deny": [],
        },
    ],
},
```

`retention_days` defines the cutoff based on event creation time. Rules select
values of the named `split_by` field. `allow` limits deletion to listed values.
`deny` excludes listed values. Use separate named instances for different
retention periods.

Before you enable a policy, reproduce its cutoff and selection as a search.
Inspect the matching events. Make sure that no legal hold or incident response
requirement applies. Start with a narrow allowlist. After deployment, inspect
the crawler logs and measure the database size. PostgreSQL can require a vacuum
operation before it can reuse the free space.

Deleting an event cascades to findings linked to that event. Preserve required
findings or extend the event policy before the cutoff is reached.
