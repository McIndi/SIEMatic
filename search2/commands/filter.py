import ast
from django.db.models import Q
from search2.engine.literals import parse_literal
from search2.engine.lookups import parse_lookup, matches


class FilterCmd:
    """Filter command for applying additional filtering conditions.
    Examples:
        filter --condition='host="server1"'
        filter --condition='created__gte="2025-10-01"'
        filter --condition='event_data__event_id=4625'
    """
    name = "filter"

    def add_arguments(self, p):
        p.add_argument(
            "--condition",
            required=True,
            help="Django ORM filter expression (e.g., 'host=\"server1\"' or 'created__gte=\"2025-10-01\"')",
        )

    def run_none(self, data, args, ctx):
        raise NotImplementedError("filter command requires input data")

    def run_qs(self, qs, args, ctx):
        """Apply filter using Django ORM."""
        try:
            field, lookup, value = parse_lookup(args.condition)
            # Convert to Django field lookup
            django_lookup = f"{field}__{lookup}" if lookup != 'exact' else field
            return qs.filter(**{django_lookup: value})
        except Exception as e:
            # If Django filtering fails, fall back to DataFrame
            from django_pandas.io import read_frame
            df = read_frame(qs)
            return self.run_df(df, args, ctx)

    def run_df(self, df, args, ctx):
        """Apply filter using pandas operations."""
        try:
            field, lookup, value = parse_lookup(args.condition)
            
            if lookup == 'exact':
                return df[df[field] == value]
            elif lookup == 'iexact':
                return df[df[field].str.lower() == str(value).lower()]
            elif lookup == 'gte':
                return df[df[field] >= value]
            elif lookup == 'lte':
                return df[df[field] <= value]
            elif lookup == 'gt':
                return df[df[field] > value]
            elif lookup == 'lt':
                return df[df[field] < value]
            elif lookup == 'icontains':
                return df[df[field].str.lower().str.contains(str(value).lower())]
            elif lookup == 'contains':
                return df[df[field].str.contains(str(value))]
            elif lookup == 'istartswith':
                return df[df[field].str.lower().str.startswith(str(value).lower())]
            elif lookup == 'startswith':
                return df[df[field].str.startswith(str(value))]
            elif lookup == 'iendswith':
                return df[df[field].str.lower().str.endswith(str(value).lower())]
            elif lookup == 'endswith':
                return df[df[field].str.endswith(str(value))]
            elif lookup == 'in':
                return df[df[field].isin(value)]
            elif lookup == 'range':
                return df[(df[field] >= value[0]) & (df[field] <= value[1])]
            else:
                raise ValueError(f"Unsupported lookup type: {lookup}")
                
        except Exception as e:
            raise ValueError(f"Invalid filter condition: {args.condition}") from e

    def run_records(self, rows, args, ctx):
        """Apply filter using dict operations."""
        try:
            field, lookup, value = parse_lookup(args.condition)
            return [r for r in rows if matches(r, field, lookup, value)]
        except Exception as e:
            raise ValueError(f"Invalid filter condition: {args.condition}") from e