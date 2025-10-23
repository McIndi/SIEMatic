import logging
from django.db.models import Count
from search2.engine.literals import parse_literal_list

logger = logging.getLogger(__name__)

class GroupByCmd:
    """GroupBy command for aggregating data.
    Examples:
        groupby --keys='["field1", "field2"]' --out='count'
        groupby --keys='["field1", "Sum(field2)"]' --out='sum'
    """
    name = "groupby"

    def add_arguments(self, p):
        p.add_argument(
            "--keys",
            required=True,
            help="""Python list/tuple literal of fields/expressions to group by, e.g. '["field1", "field2", "expr"]'"""
        )
        p.add_argument(
            "--out",
            default="count",
            help="Name of the output aggregated field (default: count)",
        )

    def run_none(self, data, args, ctx):
        raise NotImplementedError("groupby command requires input data")

    def run_qs(self, qs, args, ctx):
        from search2.engine.expression_util import parse_field_expressions, convert_to_django_expression
        keys = parse_field_expressions(parse_literal_list(args.keys, "--keys"))
        logger.debug("Parsed groupby keys: %s", keys)
        value_fields = []
        annotations = {}
        for k in keys:
            if isinstance(k, str):
                value_fields.append(k)
            elif isinstance(k, tuple):
                # Use convert_to_django_expression for dynamic aggregation
                annotations[args.out] = convert_to_django_expression(k)
        if not annotations:
            # Default to count if no aggregation specified
            from django.db.models import Count
            annotations[args.out] = Count("*")
        logger.debug("Grouping by fields: %s, annotations: %s", value_fields, annotations)
        qs = qs.values(*value_fields).annotate(**annotations)
        logger.debug("Annotated queryset with fields: %s, annotations: %s", value_fields, annotations)
        return qs

    def run_df(self, df, args, ctx):
        from search2.engine.expression_util import parse_field_expressions, convert_to_pandas_expression
        keys = parse_field_expressions(parse_literal_list(args.keys, "--keys"))
        key_names = []
        for k in keys:
            if isinstance(k, str):
                key_names.append(k)
            else:
                col_name = f"expr_{len(key_names)}"
                df[col_name] = convert_to_pandas_expression(k)
                key_names.append(col_name)
        result = df.groupby(key_names).size().reset_index(name=args.out)
        return result

    def run_records(self, rows, args, ctx):
        from search2.engine.expression_util import parse_field_expressions, convert_to_python_expression
        keys = parse_field_expressions(parse_literal_list(args.keys, "--keys"))
        key_names = [str(k) if isinstance(k, str) else k for k in keys]
        from collections import defaultdict
        counter = defaultdict(int)
        for row in rows:
            group = tuple(row.get(k) for k in key_names)
            counter[group] += 1
        result = []
        for group, count in counter.items():
            group_dict = dict(zip(key_names, group))
            group_dict[args.out] = count
            result.append(group_dict)
        return result
