import pandas as pd
import json
from textwrap import dedent
from django.db.models import F


class ExplodeCmd:
    """Explode command for flattening top-level keys of a JSON field into separate columns.
    Examples:
        explode --field=data
    """
    name = "explode"

    def add_arguments(self, p):
        p.add_argument(
            "--field",
            required=True,
            help=dedent("""
            The field containing JSON data to explode (e.g., --field=data).
            Top-level keys become new columns prefixed with the field name.
            """),
        )

    def run_none(self, data, args, ctx):
        raise NotImplementedError("explode command requires input data")

    def run_qs(self, qs, args, ctx):
        """Explode JSON field directly on QuerySet using annotate."""
        field = getattr(args, 'field')

        # Sample the first 1000 rows to get unique top-level keys from the JSON field
        sample_qs = qs[:1000]
        all_data = sample_qs.values_list(field, flat=True)
        keys = set()
        for item in all_data:
            if isinstance(item, str):
                try:
                    data = json.loads(item)
                except (json.JSONDecodeError, TypeError):
                    continue
            elif isinstance(item, dict):
                data = item
            else:
                continue
            if isinstance(data, dict):
                keys.update(data.keys())

        # Annotate the QuerySet with extracted fields, prefixed with the field name
        annotations = {f'{field}_{k}': F(f'{field}__{k}') for k in keys}
        qs = qs.annotate(**annotations)

        # Defer the original field since it's now redundant with the exploded fields
        try:
            qs = qs.defer(field)
        except (AttributeError, TypeError):
            # If defer fails (e.g., after values/values_list), skip it
            pass

        return qs

    def run_df(self, df, args, ctx):
        """Explode JSON field in DataFrame."""
        field = getattr(args, 'field')
        if field not in df.columns:
            return df

        df = df.copy()

        # Parse JSON if string
        def parse_json(x):
            if isinstance(x, str):
                try:
                    return json.loads(x)
                except (json.JSONDecodeError, TypeError):
                    return {}
            elif isinstance(x, dict):
                return x
            else:
                return {}

        df[field] = df[field].apply(parse_json)

        # Expand top-level keys
        expanded = pd.json_normalize(df[field])
        if not expanded.empty:
            # Remove the original field and add expanded columns at once using concat
            df = df.drop(columns=[field])
            expanded = expanded.add_prefix(f'{field}_')
            df = pd.concat([df, expanded], axis=1)

        return df

    def run_records(self, rows, args, ctx):
        """Convert records to DataFrame and explode JSON."""
        df = pd.DataFrame(rows)
        return self.run_df(df, args, ctx)