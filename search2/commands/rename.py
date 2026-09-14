import pandas as pd

from search2.engine.literals import parse_literal
from search2.utils import coerce_to_list_of_dicts


class RenameCmd:
    """Rename command for renaming columns.
    Examples:
        rename --mapping='{"old_name": "new_name", "field2": "field_two"}'
    """
    name = "rename"

    def add_arguments(self, p):
        p.add_argument(
            "--mapping",
            required=True,
            help="Dictionary mapping old names to new names, e.g. '{\"old_name\": \"new_name\"}'",
        )

    def run_none(self, data, args, ctx):
        raise NotImplementedError("rename command requires input data")

    def run_qs(self, qs, args, ctx):
        """Rename columns after preserving the queryset's current projection."""
        df = pd.DataFrame.from_records(coerce_to_list_of_dicts(qs))
        return self.run_df(df, args, ctx)

    def run_df(self, df, args, ctx):
        """Rename columns using pandas rename."""
        mapping = parse_literal(args.mapping, "--mapping")
        if not isinstance(mapping, dict):
            raise ValueError("--mapping must be a dictionary")
        return df.rename(columns=mapping)

    def run_records(self, rows, args, ctx):
        """Rename columns using Python dict comprehension."""
        mapping = parse_literal(args.mapping, "--mapping")
        if not isinstance(mapping, dict):
            raise ValueError("--mapping must be a dictionary")

        return [{mapping.get(k, k): v for k, v in row.items()} for row in rows]
