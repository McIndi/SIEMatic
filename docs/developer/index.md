---
title: Developer Guide
---

# Developer Guide

SIEMatic is a Django project whose runtime roles share models and configuration
but start through different management commands.

## Module map

| Path | Responsibility |
| --- | --- |
| `SIEMatic/` | URL routing and shared, web, indexer, agent, and crawler settings |
| `project/` | Custom user, profiles, authentication pages, default groups, `serve`, and `rundev` |
| `events/` | Event model, field extraction, serializers, and ingestion REST viewset |
| `indexer/` | Authenticated WebSocket consumer and indexer management command |
| `agent/` | Collection plugins, plugin process manager, sender, and agent command |
| `search2/` | Pipeline engine, registered commands, saved searches, search UI, and APIs |
| `dashboarding/` | Dashboards, panels, parameter handling, and visualizations |
| `crawlers/` | Analytics plugins, finding triage, alert plugins, retention, and crawler command |
| `templates/` | Project-level Django templates |
| `static/` | Project and vendored browser assets |

## Extension points

- Add pipeline stages through `SIEMATIC_SEARCH["COMMANDS"]`. See [Writing a
  Search Command](writing-a-search-command.md).
- Add analytics by subclassing `BaseCrawlerPlugin`. See [Writing a Crawler
  Plugin](writing-a-crawler-plugin.md).
- Add event sources as agent plugins. See [Writing an Agent
  Plugin](writing-an-agent-plugin.md).
- Add alert transports by implementing the interface in
  `crawlers.alerting.base` and registering it in `ALERTING_PLUGINS`.

## Frontend architecture

Pages are server-rendered Django templates. Reusable presentation lives under
`templates/components/` or app-specific component template directories and is
included with `{% include %}`. Dynamic chart, table, command-help, saved-search,
and visualization behavior lives in static JavaScript under `search2/static/`.
Prepare component context in views or small helpers such as
`search2.apps.generate_command_help_rows`. Do not reintroduce the removed
`django-components` template-tag system.
