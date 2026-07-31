---
title: Writing a Search Command
---

# Writing a Search Command

A search command is an instantiable class with a unique `name` and an
`add_arguments(parser)` method. It also has one or more dataset methods:
`run_none`, `run_qs`, `run_df`, and `run_records`.

```python
class SampleCmd:
    """Return the first N rows."""

    name = "sample"

    def add_arguments(self, parser):
        parser.add_argument("--n", type=int, default=10, help="Rows to return")

    def run_qs(self, queryset, args, context):
        return queryset[:args.n]

    def run_df(self, dataframe, args, context):
        return dataframe.head(args.n)

    def run_records(self, rows, args, context):
        return rows[:args.n]
```

The engine uses `run_none` when a command begins a pipeline. It uses `run_qs`
for a Django QuerySet and `run_df` for a pandas DataFrame or Series. It uses
`run_records` for a list of dictionaries. An omitted handler causes a
`NotImplementedError` for that input type. Return a supported type so the engine
can send it to the next stage.

Register the import path in `SIEMATIC_SEARCH["COMMANDS"]` in
`SIEMatic/settings/base.py`:

```python
"your_app.commands.sample:SampleCmd",
```

Keep argparse help accurate: it supplies both the search UI and generated
reference. Reuse literal and lookup parsing from `search2.engine` instead of
evaluating user input. When you load models or traverse relationships, use
`context.request` and the existing authorization helpers.

Add tests for every supported data kind, argument validation, empty input,
permissions, and output limits. Then run the Django suite and a strict
documentation build. The build shows the new command in the generated reference.
