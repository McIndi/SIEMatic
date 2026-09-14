from django.db.models.query import ValuesIterable

from search2.engine.literals import parse_literal_list


class SelectCmd:
    """Keep only selected fields in a result set.

    Example:
        select --fields='["host", "source"]'
    """

    name = "select"

    def add_arguments(self, parser):
        parser.add_argument(
            "--fields",
            required=True,
            help="Fields to keep, e.g. '[\"field1\", \"field2\"]'",
        )

    def run_none(self, data, args, ctx):
        raise NotImplementedError("select command requires input data")

    def run_qs(self, queryset, args, ctx):
        fields = self._fields(args)
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

        selected = [field for field in fields if field in visible_fields]
        if not selected:
            return [{} for _ in queryset]
        return queryset.values(*selected)

    def run_df(self, dataframe, args, ctx):
        fields = self._fields(args)
        return dataframe.loc[:, [field for field in fields if field in dataframe.columns]]

    def run_records(self, rows, args, ctx):
        fields = self._fields(args)
        return [
            {field: row[field] for field in fields if field in row}
            for row in rows
        ]

    @staticmethod
    def _fields(args):
        fields = parse_literal_list(args.fields, "--fields")
        if not all(isinstance(field, str) for field in fields):
            raise ValueError("--fields must contain only field names")
        return fields