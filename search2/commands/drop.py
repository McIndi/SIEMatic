from django.db.models.query import ValuesIterable

from search2.engine.literals import parse_literal_list


def drop_queryset_fields(queryset, fields):
    """Project a queryset to every currently visible field except ``fields``."""
    dropped = set(fields)
    query = queryset.query

    if queryset._iterable_class is ValuesIterable:
        visible_fields = [
            *query.extra_select,
            *query.values_select,
            *query.annotation_select,
        ]
    else:
        visible_fields = [field.name for field in queryset.model._meta.concrete_fields]
        visible_fields.extend(query.annotation_select)

    # dict.fromkeys keeps the existing projection order and removes any alias
    # that appears in more than one of Django's internal select collections.
    kept_fields = [
        field for field in dict.fromkeys(visible_fields) if field not in dropped
    ]
    if not kept_fields:
        # values() with no arguments means "select every model field" in
        # Django. Materialize empty records to represent a true zero-column
        # result instead.
        return [{} for _ in queryset]
    return queryset.values(*kept_fields)


class DropCmd:
    """Remove one or more fields from a result set.

    Examples:
        drop --fields='["raw", "internal_id"]'
    """

    name = "drop"

    def add_arguments(self, parser):
        parser.add_argument(
            "--fields",
            required=True,
            help="Fields to remove, e.g. '[\"field1\", \"field2\"]'",
        )

    def run_none(self, data, args, ctx):
        raise NotImplementedError("drop command requires input data")

    def run_qs(self, queryset, args, ctx):
        fields = self._fields(args)
        return drop_queryset_fields(queryset, fields)

    def run_df(self, dataframe, args, ctx):
        fields = self._fields(args)
        return dataframe.drop(columns=fields, errors="ignore")

    def run_records(self, rows, args, ctx):
        fields = set(self._fields(args))
        return [
            {key: value for key, value in row.items() if key not in fields}
            for row in rows
        ]

    @staticmethod
    def _fields(args):
        fields = parse_literal_list(args.fields, "--fields")
        if not all(isinstance(field, str) for field in fields):
            raise ValueError("--fields must contain only field names")
        return fields
