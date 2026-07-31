---
title: Search and Dashboards
---

# Search and Dashboards

SIEMatic's search UI is at `/search2/`. A query is a sequence of commands
separated by `|`. Each command receives data from the previous command. It
returns a QuerySet, pandas DataFrame, or list of records for the next stage.

Start with [Search Language](search-language.md), then use [Saved Searches and
Sharing](saved-searches-and-sharing.md) for reusable queries and [Building
Dashboards](building-dashboards.md) for multi-panel views. The UI includes
command help generated from the same registry as the [Search Command
Reference](../reference/search-commands.md).

Searches run with the authenticated user's model permissions. The pipeline
cannot query user or saved-search models, and traversing related models requires
view permission for each model. Result sets are capped by
`SIEMATIC_SEARCH["MAX_ROWS"]`, which defaults to 10,000.
