---
title: Crawler Configuration
---

# Crawler Configuration

Crawler plugins analyze stored events in separate processes. The configuration
is in `SIEMatic/settings/crawler.py`. Restart the crawler service after you
change this file.

## Register plugins and instances

`CRAWLER_PLUGINS` contains import paths for available plugin classes.
`CRAWLER_CONFIGS` contains named instances. Multiple instances can use the same
plugin with different schedules, databases, or rules.

```python
CRAWLER_PLUGINS = [
    "crawlers.plugins.failed_login_crawler.FailedLoginCrawler",
]

CRAWLER_CONFIGS = {
    "failed_login_crawler": {
        "name": "failed_login_crawler",
        "enabled": True,
        "type": "daemon",
        "restart": True,
        "interval": 60,
        "realert_cooldown": 86400,
        "db_alias": "default",
        "alerting_plugins": ["email_alert"],
    },
}
```

Common keys are:

- `name`: plugin name that matches the instance to a loaded class
- `enabled`: controls whether the process manager starts the instance
- `type`: `daemon` for a long-running loop or `scheduled` for one execution per
  cron occurrence
- `restart`: restart policy for daemon failures (`True`, `False`, or a maximum
  count)
- `interval`: polling delay used by a daemon plugin
- `schedule`: five-field cron expression used by a scheduled instance
- `db_alias`: Django database alias queried by plugin helpers
- `realert_cooldown`: seconds before the same rule can create another finding
  for the same event
- `alerting_plugins`: names of configured alert senders

Plugin-specific keys, including retention `rules`, are passed through unchanged.

## Run and check

Run all enabled instances indefinitely:

```bash
python manage.py run_crawlers --settings SIEMatic.settings.crawler
```

Run one named plugin while validating a change:

```bash
python manage.py run_crawlers --plugin failed_login_crawler --settings SIEMatic.settings.crawler
```

Inspect logs for import failures, invalid schedules, database errors, and alert
delivery failures. Test a production change against non-production events before
deployment.
