---
title: Building Dashboards
---

# Building Dashboards

Open `/dashboarding/` to create a dashboard owned by the current user. A
dashboard contains a name, description, optional parameter defaults, and an
ordered set of panels.

## Create panels

Each panel accepts a raw pipeline or the name of a saved search. Choose a table
or chart visualization. Charts also use a chart type, x field, y field, and
optional grouping field. Before you save the panel, use its preview. Make sure
that the query and field names are correct.

For a useful first panel, try a table with:

```pipeline
search --filter='created__gte={last_hour}' --order-by='["-created"]' --limit=100
```

Panel order is numeric. Dashboard and panel access is currently owner-scoped in
the dashboard UI. There is no dashboard sharing or per-dashboard export/import
workflow.

## Dashboard parameters

Panel queries can use Python format placeholders. SIEMatic collects placeholders
across the panels and displays a form when the dashboard opens. A format suffix
ending in `d` creates an integer input. The suffix `f`, `e`, or `g` creates a
floating-point input. Other placeholders are text.

For example, this query prompts for a numeric limit:

```pipeline
search --filter='index="sysmon"' --order-by='["-created"]' --limit={row_count:d}
```

Store defaults as a JSON object on the dashboard, such as
`{"row_count": 25}`. Parameter values are formatted into the pipeline before it
runs. Dashboard authors must control who can edit dashboards. Test every
parameterized query with expected values and boundary values.
