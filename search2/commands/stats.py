import logging
from django.db.models import Count
from search2.engine.literals import parse_literal_list
from search2.engine.expression_util import parse_field_expressions, convert_to_django_expression, SUPPORTED_FUNCTIONS

logger = logging.getLogger(__name__)


AGGREGATION_FUNCTIONS = {
    "sum": "Sum",
    "avg": "Avg",
    "count": "Count",
    "max": "Max",
    "min": "Min",
    "stddev": "StdDev",
    "variance": "Variance",
}


class StatsCmd:
    """Stats command for computing statistics over a result set.
    Examples:
        stats --aggregations='["count"]'
        stats --aggregations='["count", "avg(duration)", "max(size)"]' --by='["host"]'
        stats --aggregations='["sum(bytes)", "min(bytes)", "max(bytes)"]' --by='["source", "destination"]'
    """
    name = "stats"

    def add_arguments(self, p):
        p.add_argument(
            "--aggregations",
            required=True,
            help="""Python list literal of aggregation expressions. Count, Sum, Avg, Min, and Max work for all backends; StdDev and Variance require QuerySets. Function names are case-insensitive."""
        )
        p.add_argument(
            "--by",
            help="""Python list literal of fields to group by, e.g. '["field1", "field2"]'"""
        )

    def run_none(self, data, args, ctx):
        raise NotImplementedError("stats command requires input data")

    def run_qs(self, qs, args, ctx):
        aggregations = self._aggregations(args)
        logger.debug("Parsed aggregations: %s", aggregations)
        
        annotations = {}
        for i, agg in enumerate(aggregations):
            if isinstance(agg, str):
                if agg.lower() == 'count':
                    annotations[f'count_{i}'] = Count('*')
                else:
                    raise ValueError(f"Unsupported aggregation: {agg}")
            elif isinstance(agg, tuple):
                # Assume it's a function call like ('Avg', ['field'], {})
                func_name, func_args, func_kwargs = agg
                if func_name in SUPPORTED_FUNCTIONS and 'qs' in SUPPORTED_FUNCTIONS[func_name]:
                    if func_args:
                        # For aggregations with field
                        annotations[f'{func_name.lower()}_{func_args[0]}_{i}'] = convert_to_django_expression(agg)
                    else:
                        # For aggregations without field, like Count()
                        annotations[f'{func_name.lower()}_{i}'] = convert_to_django_expression(agg)
                else:
                    raise ValueError(f"Unsupported aggregation function: {func_name}")
            else:
                raise ValueError(f"Unsupported aggregation expression: {agg}")
        
        group_by_fields = []
        if args.by:
            group_by = parse_literal_list(args.by, "--by")
            group_by_fields = [f for f in group_by if isinstance(f, str)]
        
        if group_by_fields:
            qs = qs.values(*group_by_fields).annotate(**annotations)
        else:
            # Overall stats, no group by
            try:
                qs = qs.aggregate(**annotations)
            except Exception as e:
                qs = qs.annotate(**annotations)
                return qs
            # Aggregate returns a dict, but we need to return a queryset-like, so convert to list of dict
            return [qs]
        
        return qs

    def run_df(self, df, args, ctx):
        import pandas as pd
        aggregations = self._aggregations(args)
        
        group_by_fields = []
        if args.by:
            group_by = parse_literal_list(args.by, "--by")
            group_by_fields = [f for f in group_by if isinstance(f, str)]
        
        if group_by_fields:
            # Grouped stats
            grouped = df.groupby(group_by_fields, dropna=False)
            result = grouped.size().reset_index().iloc[:, :len(group_by_fields)]
            for i, agg in enumerate(aggregations):
                if isinstance(agg, str):
                    if agg.lower() == 'count':
                        result[f'count_{i}'] = grouped.size().to_numpy()
                    else:
                        raise ValueError(f"Unsupported aggregation: {agg}")
                elif isinstance(agg, tuple):
                    func_name, func_args, func_kwargs = agg
                    func_entry = SUPPORTED_FUNCTIONS.get(func_name)
                    if func_entry and 'df' in func_entry and func_args:
                        field = func_args[0]
                        result[f'{func_name.lower()}_{field}_{i}'] = (
                            grouped[field].agg(func_entry['df']).to_numpy()
                        )
                    else:
                        raise ValueError(f"Unsupported aggregation: {agg}")
            return result
        else:
            # Overall stats
            result = {}
            for i, agg in enumerate(aggregations):
                if isinstance(agg, str):
                    if agg.lower() == 'count':
                        result[f'count_{i}'] = len(df)
                    else:
                        raise ValueError(f"Unsupported aggregation: {agg}")
                elif isinstance(agg, tuple):
                    func_name, func_args, func_kwargs = agg
                    func_entry = SUPPORTED_FUNCTIONS.get(func_name)
                    if func_entry and 'df' in func_entry and func_args:
                        field = func_args[0]
                        series = df[field]
                        result[f'{func_name.lower()}_{field}_{i}'] = func_entry['df'](series)
                    else:
                        raise ValueError(f"Unsupported aggregation: {agg}")
            return [result]

    def run_records(self, rows, args, ctx):
        aggregations = self._aggregations(args)
        
        group_by_fields = []
        if args.by:
            group_by = parse_literal_list(args.by, "--by")
            group_by_fields = [f for f in group_by if isinstance(f, str)]
        
        if group_by_fields:
            from collections import defaultdict
            groups = defaultdict(list)
            for row in rows:
                key = tuple(row.get(f) for f in group_by_fields)
                groups[key].append(row)
            
            results = []
            for key, group_rows in groups.items():
                result = dict(zip(group_by_fields, key))
                for i, agg in enumerate(aggregations):
                    if isinstance(agg, str):
                        if agg.lower() == 'count':
                            result[f'count_{i}'] = len(group_rows)
                        else:
                            raise ValueError(f"Unsupported aggregation: {agg}")
                    elif isinstance(agg, tuple):
                        func_name, func_args, func_kwargs = agg
                        func_entry = SUPPORTED_FUNCTIONS.get(func_name)
                        if func_entry and 'records' in func_entry and func_args:
                            field = func_args[0]
                            values = [r.get(field) for r in group_rows if r.get(field) is not None]
                            result[f'{func_name.lower()}_{field}_{i}'] = func_entry['records'](values)
                        else:
                            raise ValueError(f"Unsupported aggregation: {agg}")
                results.append(result)
            return results
        else:
            # Overall stats
            result = {}
            for i, agg in enumerate(aggregations):
                if isinstance(agg, str):
                    if agg.lower() == 'count':
                        result[f'count_{i}'] = len(rows)
                    else:
                        raise ValueError(f"Unsupported aggregation: {agg}")
                elif isinstance(agg, tuple):
                    func_name, func_args, func_kwargs = agg
                    func_entry = SUPPORTED_FUNCTIONS.get(func_name)
                    if func_entry and 'records' in func_entry and func_args:
                        field = func_args[0]
                        values = [r.get(field) for r in rows if r.get(field) is not None]
                        result[f'{func_name.lower()}_{field}_{i}'] = func_entry['records'](values)
                    else:
                        raise ValueError(f"Unsupported aggregation: {agg}")
            return [result]

    @staticmethod
    def _aggregations(args):
        expressions = parse_field_expressions(
            parse_literal_list(args.aggregations, "--aggregations")
        )
        normalized = []
        for expression in expressions:
            if isinstance(expression, tuple):
                function_name, function_args, function_kwargs = expression
                canonical_name = AGGREGATION_FUNCTIONS.get(function_name.lower())
                if not canonical_name:
                    raise ValueError(f"Unsupported aggregation function: {function_name}")
                normalized.append((canonical_name, function_args, function_kwargs))
            else:
                normalized.append(expression)
        return normalized