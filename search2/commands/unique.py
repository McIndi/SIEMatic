from search2.engine.literals import parse_literal_list


class UniqueCmd:
    """Unique command for getting distinct values for fields.
    Examples:
        unique --fields='["host"]'
        unique --fields='["host", "sourcetype"]'
    """
    name = "unique"

    def add_arguments(self, p):
        p.add_argument(
            "--fields",
            required=True,
            help="Fields to get unique values for, e.g. '[\"field1\", \"field2\"]'",
        )

    def run_none(self, data, args, ctx):
        raise NotImplementedError("unique command requires input data")

    def run_qs(self, qs, args, ctx):
        """Get unique values using Django ORM distinct."""
        fields = parse_literal_list(args.fields, "--fields")
        return qs.values(*fields).distinct()

    def run_df(self, df, args, ctx):
        """Get unique values using pandas drop_duplicates."""
        fields = parse_literal_list(args.fields, "--fields")
        return df[fields].drop_duplicates()

    def run_records(self, rows, args, ctx):
        """Get unique values using Python set."""
        fields = parse_literal_list(args.fields, "--fields")
        seen = set()
        result = []
        for row in rows:
            key = tuple(row.get(field) for field in fields)
            if key not in seen:
                seen.add(key)
                result.append(row)
        return result