from search2.engine.literals import parse_literal
from search2.utils import coerce_to_list_of_dicts


class FillNullCmd:
    """Replace null values in a result field.

    Example:
        fillnull --field=host --value=unknown
    """

    name = "fillnull"

    def add_arguments(self, parser):
        parser.add_argument("--field", required=True, help="Field whose null values to replace")
        parser.add_argument("--value", required=True, help="Replacement value")

    def run_none(self, data, args, ctx):
        raise NotImplementedError("fillnull command requires input data")

    def run_qs(self, queryset, args, ctx):
        return self.run_records(coerce_to_list_of_dicts(queryset), args, ctx)

    def run_df(self, dataframe, args, ctx):
        result = dataframe.copy()
        if args.field in result.columns:
            result[args.field] = result[args.field].where(
                result[args.field].notna(), self._value(args)
            )
        return result

    def run_records(self, rows, args, ctx):
        value = self._value(args)
        return [
            {
                key: value if key == args.field and current is None else current
                for key, current in row.items()
            }
            for row in rows
        ]

    @staticmethod
    def _value(args):
        return parse_literal(args.value, "--value")