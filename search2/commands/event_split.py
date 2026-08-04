from django.db.models.query import (
    FlatValuesListIterable,
    ValuesIterable,
    ValuesListIterable,
)


def _is_array(value):
    """Return whether a value is an array that event_split can expand."""
    return isinstance(value, (list, tuple))


def _split_records(rows, field):
    """Split array values into records without changing the input records."""
    result = []
    for row in rows:
        value = row.get(field)
        if not _is_array(value):
            result.append(dict(row))
            continue
        for item in value:
            split_row = dict(row)
            split_row[field] = item
            result.append(split_row)
    return result


def _queryset_records(queryset):
    """Materialize model, values, and values_list querysets as records."""
    iterable_class = queryset._iterable_class
    if issubclass(iterable_class, ValuesIterable):
        return list(queryset)

    if issubclass(iterable_class, (ValuesListIterable, FlatValuesListIterable)):
        names = [
            *queryset.query.extra_select,
            *queryset.query.values_select,
            *queryset.query.annotation_select,
        ]
        if issubclass(iterable_class, FlatValuesListIterable):
            return [{names[0]: value} for value in queryset]
        return [dict(zip(names, values)) for values in queryset]

    return list(queryset.values())


class EventSplitCmd:
    """Split each item in an array field into a separate event."""

    name = "event_split"

    def add_arguments(self, parser):
        parser.add_argument(
            "--field",
            required=True,
            help="Array field to split into separate events, e.g. --field=tags",
        )

    def run_none(self, data, args, ctx):
        raise NotImplementedError("event_split command requires input data")

    def run_qs(self, queryset, args, ctx):
        """Materialize a QuerySet, then split its array values into records."""
        return _split_records(_queryset_records(queryset), args.field)

    def run_df(self, dataframe, args, ctx):
        """Split array values while preserving the DataFrame backend."""
        if args.field not in dataframe.columns:
            return dataframe.copy()

        empty_arrays = dataframe[args.field].map(
            lambda value: _is_array(value) and len(value) == 0
        )
        return dataframe.loc[~empty_arrays].explode(args.field)

    def run_records(self, rows, args, ctx):
        """Split array values while preserving the records backend."""
        return _split_records(rows, args.field)
