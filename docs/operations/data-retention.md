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
Examine the matching events. Make sure that no legal hold or incident response
requirement applies. Start with a narrow allowlist. After deployment, examine
the crawler logs. Then measure the database size. PostgreSQL can require a
vacuum operation before it can reuse the free space.

## Finding preservation

An actionable finding preserves its event. The actionable statuses are `new`,
`acknowledged`, and `in_progress`. The retention crawler skips an event if any
linked finding has one of these statuses.

The terminal statuses are `resolved` and `false_positive`. If all linked
findings are terminal, the event becomes eligible for deletion. The event must
also match the retention cutoff and policy rules. An event without findings is
eligible if it matches the same cutoff and rules.

The retention crawler deletes an eligible event and all findings linked to that
event. It does not delete an event immediately after a status change. The next
applicable retention run deletes the event.
