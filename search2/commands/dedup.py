from search2.engine.literals import parse_literal_list
from search2.utils import coerce_to_list_of_dicts


class DedupCmd:
    """Dedup command for keeping one full row per group of field values.

    Unlike unique, keeps every column, not just the named fields. Use --keep
    to choose the first or last occurrence within each group.

    Examples:
        dedup --fields='["host"]'
        dedup --fields='["host"]' --keep='last'
    """

    name = "dedup"

    def add_arguments(self, parser):
        parser.add_argument(
            "--fields",
            required=True,
            help="Fields whose combined values define a group, e.g. '[\"field1\", \"field2\"]'",
        )
        parser.add_argument(
            "--keep",
            default="first",
            choices=["first", "last"],
            help="Which occurrence to keep within each group (default: first)",
        )

    def run_none(self, data, args, ctx):
        raise NotImplementedError("dedup command requires input data")

    def run_qs(self, queryset, args, ctx):
        return self.run_records(coerce_to_list_of_dicts(queryset), args, ctx)

    def run_df(self, dataframe, args, ctx):
        fields = parse_literal_list(args.fields, "--fields")
        return dataframe.drop_duplicates(subset=fields, keep=args.keep)

    def run_records(self, rows, args, ctx):
        fields = parse_literal_list(args.fields, "--fields")
        if args.keep == "first":
            seen = set()
            result = []
            for row in rows:
                key = tuple(row.get(field) for field in fields)
                if key not in seen:
                    seen.add(key)
                    result.append(row)
            return result

        last_index = {}
        for index, row in enumerate(rows):
            key = tuple(row.get(field) for field in fields)
            last_index[key] = index
        keep_indices = set(last_index.values())
        return [row for index, row in enumerate(rows) if index in keep_indices]
