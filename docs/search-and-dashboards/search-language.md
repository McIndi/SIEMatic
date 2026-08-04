---
title: Search Language
---

# Search Language

A pipeline consists of commands separated by a pipe character. Arguments are
parsed with shell-style quoting and each command transforms the current dataset.

```pipeline
search --filter='index="sysmon"' --select='["created","host","source"]' --order-by='["-created"]' --limit=100 | head --n=20
```

The `search` command starts from a Django model (by default `events.Event`).
Later stages can remain database-backed or convert the data to pandas or Python
records. Put selective database filters and projections early in the pipeline.

## Filters and list arguments

Repeat `--filter` or `--exclude` for multiple Django-style lookup expressions.
List-valued flags such as `--select`, `--order-by`, `--keys`, and `--on` must be
Python list or tuple literals inside a quoted command argument.

```pipeline
search --filter='created__gte={last_7_days}' --exclude='host="lab-host"' --select='["created","host","index"]' --order-by='["-created"]'
```

Supported lookup names are controlled by `SIEMATIC_SEARCH["ALLOWED_LOOKUPS"]`.
They include equality, text containment and prefix/suffix matching, comparison,
`in`, and `range` variants. The authenticated user must have view permission
for the queried model and any traversed related model.

## Time placeholders

Arguments can contain placeholders that SIEMatic expands when a pipeline begins:

- `{now}`, `{today}`, `{yesterday}`, and `{timezone}`
- `{this_minute}`, `{last_minute}`, `{this_hour}`, and `{last_hour}`
- `{this_day}`, `{last_day}`, `{this_week}`, and `{last_week}`
- `{this_month}`, `{last_month}`, `{this_year}`, and `{last_year}`
- `{last_7_days}` and `{last_30_days}`.

These values are timezone-aware where appropriate. For example:

```pipeline
search --filter='created__gte={last_day}' --order-by='["-created"]' --limit=100
```

## Transformations

Registered commands include `annotate`, `filter`, `groupby`, `stats`, `sort`,
`rename`, `unique`, `explode`, `event_split`, `drop`, `to_dataframe`, `head`,
`tail`, `join`, and `run_saved_search`. The command reference contains argument
details.

`explode --field=details` promotes the top-level keys in `details` to columns
such as `details_action` and removes `details`. Use
`drop --fields='["raw", "internal_id"]'` to remove several fields explicitly.

`event_split --field=tags` creates one event for each item in the `tags` array.
Each new event keeps the values from the source event. The `tags` field contains
one array item in each new event.

```pipeline
event_split --field=tags
```

The command keeps an event unchanged if `tags` is missing or is not an array.
An empty array produces no events. For a DataFrame, the command returns a
DataFrame. For Python records, the command returns records. The command
materializes a Django QuerySet and returns records because row expansion is not
portable across database engines.

Expressions support an allowlist of Django functions. The list includes
aggregation, string, math, date/time, JSON, and utility functions. Examples are
`Avg`, `Sum`, `Count`, `Min`, `Max`, `Lower`, `Upper`, `Length`, `Round`, `Now`,
`TruncDate`, `F`, `Q`, and `Value`. Support differs by dataset backend. A
function that supports a Django QuerySet can lack an equivalent for DataFrames
or records.

## Cross-database joins

The `join` command is implemented and queries its right-hand model through the
chosen Django database alias before merging with pandas:

```pipeline
search --using='default' --select='["id","host","index"]' --limit=500 | join --using='archive' --model='events.Event' --select='["id","host","source"]' --on='["host"]' --how='left' --limit=500
```

Both sides are materialized in memory. Filter, project, and limit data before a
join. Large joins can consume substantial CPU and memory.

## Practical limitations

- JSON values used for numeric aggregation must be stored as numeric types.
- DataFrame conversion can consume significant memory on large results.
- Date inference in summary statistics uses the ordered `strptime` format list
  in `SIEMATIC_SEARCH["SUMMARY_DATE_FORMATS"]`. Add a format to that setting
  when search results use a custom date representation.
- Numeric mode can be absent when every value is unique.
- Text summaries show only the three most common values.
