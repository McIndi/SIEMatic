---
title: Saved Searches and Sharing
---

# Saved Searches and Sharing

Open `/search2/savedsearches/` to create and manage reusable pipelines. A saved
search has a name, query, owner, optional shared users, and a public flag.

## Visibility and ownership

- A private search is visible only to its owner.
- A shared search is visible to its owner and selected users.
- A public search is visible to authenticated users.
- Only the owner can edit or delete a saved search through the UI or REST API.

Use **Preview** on the create or edit form to run the query before saving. A
preview obeys the current user's pipeline permissions.

Run a visible saved search from the search UI or as a pipeline stage:

```pipeline
run_saved_search "Recent Sysmon Events"
```

Use an unambiguous saved-search name. The `run_saved_search` command resolves a
query by name and visibility. Avoid recursive saved searches.

SIEMatic does not provide per-search export/import, parameter declarations, or
version history. Whole-project Django `dumpdata` and `loaddata` can include
saved searches as part of a broader data transfer. See [Backup and
Restore](../operations/backup-and-restore.md).
