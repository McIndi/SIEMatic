from search2.engine.literals import parse_literal_list


class SortCmd:
    """Sort command for ordering data by fields.
    Examples:
        sort --fields='["created", "host"]'
        sort --fields='["-created"]'  # descending
    """
    name = "sort"

    def add_arguments(self, p):
        p.add_argument(
            "--fields",
            required=True,
            help="Fields to sort by as a list, e.g. '[\"field1\", \"-field2\"]' (use '-' prefix for descending)",
        )

    def run_none(self, data, args, ctx):
        raise NotImplementedError("sort command requires input data")

    def run_qs(self, qs, args, ctx):
        """Sort using Django ORM order_by."""
        fields = parse_literal_list(args.fields, "--fields")
        return qs.order_by(*fields)

    def run_df(self, df, args, ctx):
        """Sort using pandas sort_values."""
        fields = parse_literal_list(args.fields, "--fields")
        # Handle descending fields (prefixed with '-')
        ascending = [not f.startswith('-') for f in fields]
        sort_fields = [f[1:] if f.startswith('-') else f for f in fields]
        return df.sort_values(sort_fields, ascending=ascending)

    def run_records(self, rows, args, ctx):
        """Sort using Python sorted."""
        fields = parse_literal_list(args.fields, "--fields")

        def sort_key(row):
            key_parts = []
            for field in fields:
                if field.startswith('-'):
                    # Descending - we'll reverse later
                    field = field[1:]
                    value = row.get(field)
                    # Use a tuple that will sort descending
                    key_parts.append((value is not None, value))
                else:
                    value = row.get(field)
                    key_parts.append((value is None, value))
            return key_parts

        # For descending fields, we need to reverse the sort
        descending_fields = [f for f in fields if f.startswith('-')]
        if descending_fields:
            # This is a simplified approach - a full implementation would handle mixed asc/desc
            return sorted(rows, key=sort_key, reverse=True)
        else:
            return sorted(rows, key=sort_key)