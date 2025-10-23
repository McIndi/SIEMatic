import ast
import logging
from django.apps import apps
from django.conf import settings
from search2.engine.literals import parse_literal_list
from search2.engine.lookups import parse_lookup
from search2.engine.introspect import related_models_from_paths

logger = logging.getLogger(__name__)

from search2.engine.authz import get_authz_check


def expr_to_order_str(expr):
    if isinstance(expr, tuple) and expr[0] == 'UnaryOp' and isinstance(expr[2], ast.USub):
        return '-' + str(expr[1])
    elif isinstance(expr, str):
        return expr
    else:
        return str(expr)

def handle_select_expressions(select_exprs, backend, df_or_row=None):
    """
    backend: 'qs', 'df', or 'records'
    df_or_row: DataFrame (for 'df') or dict (for 'records'), or None
    Returns: list of field names (for 'qs'), DataFrame (for 'df'), or dict (for 'records')
    """
    from search2.engine.expression_util import generate_keyword_args, convert_to_pandas_expression, convert_to_python_expression
    if backend == 'qs':
        _, select_kwargs = generate_keyword_args(select_exprs)
        if select_kwargs:
            return 'annotate', select_kwargs
        else:
            return 'values', [str(e) if isinstance(e, str) else e for e in select_exprs]
    elif backend == 'df':
        cols = []
        for expr in select_exprs:
            if isinstance(expr, str):
                cols.append(expr)
            else:
                col_name = f"expr_{len(cols)}"
                df_or_row[col_name] = convert_to_pandas_expression(expr)
                cols.append(col_name)
        return df_or_row[cols]
    elif backend == 'records':
        def select_row(row):
            result = {}
            for expr in select_exprs:
                if isinstance(expr, str):
                    result[expr] = row.get(expr)
                else:
                    col_name = f"expr_{len(result)}"
                    result[col_name] = convert_to_python_expression(expr)
            return result
        return select_row
    else:
        raise ValueError(f"Unknown backend: {backend}")

DEFAULT_MODEL = "events.Event"
DEFAULT_USING = "default"
class SearchCmd:
    """Search command for querying events.

    Examples:
        search --filter='created__gte="2025-01-01"' --select='["created","host"]' --order-by='["-created"]' --limit=100
        annotate --set='avg_duration=Avg("duration")' --set='lower_host=Lower("host")'
        groupby --keys='["host"]' --out='total_events'
    """
    name = "search"

    def add_arguments(self, p):
        p.add_argument(
            "--using",
            default=DEFAULT_USING,
            help="Database alias to use (default: default)",
        )
        p.add_argument(
            "--model",
            default=DEFAULT_MODEL,
            help="Django model to query, in app_label.ModelName format (default: events.Event)",
        )
        p.add_argument(
            "--filter",
            action="append",
            default=[],
            help="Django ORM filter expression, e.g. 'field__lookup=value'",
        )
        p.add_argument(
            "--exclude",
            action="append",
            default=[],
            help="Django ORM exclude expression, e.g. 'field__lookup=value'",
        )
        p.add_argument(
            "--select",
            default=None,
            help="""Django ORM select expression, e.g. '["field1", "field2"]'""",
        )
        p.add_argument(
            "--order-by",
            default=None,
            help="""Django ORM order by expression, e.g. '["-field1", "field2"]'""",
        )
        p.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Limit the number of results returned",
        )

    # ---- QuerySet path (primary) ----
    def run_none(self, data, args, ctx):
        logger.debug("No input data, creating base QuerySet")
        try:
            app_label, model_name = args.model.split(".", 1)
        except ValueError:
            raise ValueError("--model must be 'app_label.ModelName'")
        logger.debug("Resolving model %s:%s", app_label, model_name)
        Model = apps.get_model(app_label, model_name)
        logger.debug("Resolved model: %s", Model)
        if not Model:
            logger.exception("Unknown model '%s'", args.model)
            raise ValueError(f"Unknown model '{args.model}'")
        qs = Model.objects.all()
        logger.debug("Initial QuerySet: %s", qs.query)
        if args.using:
            logger.debug("Using DB alias: %s", args.using)
            qs = qs.using(args.using)
        logger.debug("Passing QuerySet to run_qs")
        return self.run_qs(qs, args, ctx)

    def run_qs(self, qs, args, ctx):
        # Base model resolution
        logger.debug("Starting run_qs with QuerySet: %s", qs.query)
        if args.model:
            logger.debug("Resolving model %s", args.model)
            try:
                app_label, model_name = args.model.split(".", 1)
            except ValueError:
                raise ValueError("--model must be 'app_label.ModelName'")
            logger.debug("Getting model %s:%s", app_label, model_name)
            Model = apps.get_model(app_label, model_name)
            logger.debug("Resolved model: %s", Model)
            if not Model:
                logger.exception("Unknown model '%s'", args.model)
                raise ValueError(f"Unknown model '{args.model}'")
            qs = Model.objects.all()
            logger.debug("New base QuerySet: %s", qs.query)
            base_model = Model
            logger.debug("Base model set to: %s", base_model)
        else:
            base_model = qs.model
            logger.debug("Using existing QuerySet model as base model: %s", base_model)

        # DB alias
        if args.using:
            logger.debug("Using DB alias: %s", args.using)
            qs = qs.using(args.using)

        # Collect field paths for authz traversal checks
        paths = []
        for expr in (args.filter or []) + (args.exclude or []):
            logger.debug("Parsing lookup expression: %s", expr)
            field_path, _, _ = parse_lookup(expr)
            paths.append(field_path)
            logger.debug("Resolved field path: %s", len(paths))
        if args.select:
            logger.debug("Parsing select expression: %s", args.select)
            paths += [s for s in parse_literal_list(args.select, "--select")]
            logger.debug("Resolved select paths: %d", len(paths))
        if args.order_by:
            logger.debug("Parsing order_by expression: %s", args.order_by)
            paths += [s.lstrip("-") for s in parse_literal_list(args.order_by, "--order-by")]
            logger.debug("Resolved order_by paths: %d", len(paths))

        # Authorization
        logger.debug("Performing authorization check")
        get_authz_check()(ctx.request, base_model, related_models_from_paths(base_model, paths))
        logger.debug("Authorization check passed")

        # Apply filters/excludes
        for expr in args.filter or []:
            logger.debug("Parsing filter expression: %s", expr)
            f, l, v = parse_lookup(expr)
            logger.debug("Resolved filter expression: %s %s %s", f, l, v)
            key = f if l == "exact" else f"{f}__{l}"
            logger.debug("Applying filter: %s", key)
            qs = qs.filter(**{key: v})
        for expr in args.exclude or []:
            logger.debug("Parsing exclude expression: %s", expr)
            f, l, v = parse_lookup(expr)
            logger.debug("Resolved exclude expression: %s %s %s", f, l, v)
            key = f if l == "exact" else f"{f}__{l}"
            logger.debug("Applying exclude: %s", key)
            qs = qs.exclude(**{key: v})

        # Order & projection with expression support
        from search2.engine.expression_util import parse_field_expressions, generate_keyword_args
        if args.order_by:
            logger.debug("Handling order_by expressions")
            order_exprs = parse_field_expressions(parse_literal_list(args.order_by, "--order-by"))
            logger.debug("Resolved order expressions: %s", order_exprs)
            qs = qs.order_by(*[expr_to_order_str(e) for e in order_exprs])
        if args.select:
            logger.debug("Handling select expressions")
            select_exprs = parse_field_expressions(parse_literal_list(args.select, "--select"))
            logger.debug("Resolved select expressions: %s", select_exprs)
            sel_type, sel_val = handle_select_expressions(select_exprs, 'qs')
            logger.debug("Select type: %s, value: %s", sel_type, sel_val)
            if sel_type == 'annotate':
                logger.debug("Applying annotations: %s", sel_val)
                qs = qs.annotate(**sel_val).values(*sel_val.keys())
            else:
                logger.debug("Applying values: %s", sel_val)
                qs = qs.values(*sel_val)
        if args.limit is not None:
            logger.debug("Applying limit: %d", args.limit)
            qs = qs[:args.limit]
        # Limit with cap
        # search_settings = getattr(settings, "SIEMATIC_SEARCH", {})
        # cap = search_settings.get("MAX_ROWS", 10_000)
        # if cap is None or cap <= 0 or args.limit == 0:
        #     return qs
        # n = min(args.limit, cap) if args.limit is not None else cap
        # if n is not None:
        #     logger.debug("Applying limit: %d", n)
        #     qs = qs[:n]
        return qs

    # ---- DataFrame path ----
    def run_df(self, df, args, ctx):
        import pandas as pd
        if not args.model == DEFAULT_MODEL or not args.using == DEFAULT_USING:
            raise ValueError("--model/--using are not supported for in-memory datasets")

        # Filtering
        for expr in args.filter or []:
            f, l, v = parse_lookup(expr)
            col = f if l == "exact" else f
            if l == "exact":
                df = df[df[col] == v]
            elif l == "in":
                df = df[df[col].isin(v)]
            elif l == "contains":
                df = df[df[col].str.contains(v)]
            elif l == "gt":
                df = df[df[col] > v]
            elif l == "gte":
                df = df[df[col] >= v]
            elif l == "lt":
                df = df[df[col] < v]
            elif l == "lte":
                df = df[df[col] <= v]
            # Add more lookups as needed

        # Excluding
        for expr in args.exclude or []:
            f, l, v = parse_lookup(expr)
            col = f if l == "exact" else f
            if l == "exact":
                df = df[df[col] != v]
            elif l == "in":
                df = df[~df[col].isin(v)]
            elif l == "contains":
                df = df[~df[col].str.contains(v)]
            elif l == "gt":
                df = df[df[col] <= v]
            elif l == "gte":
                df = df[df[col] < v]
            elif l == "lt":
                df = df[df[col] >= v]
            elif l == "lte":
                df = df[df[col] > v]
            # Add more lookups as needed

        # Select (projection) with expression support
        from search2.engine.expression_util import parse_field_expressions, generate_keyword_args, convert_to_pandas_expression
        if args.select:
            select_exprs = parse_field_expressions(parse_literal_list(args.select, "--select"))
            df = handle_select_expressions(select_exprs, 'df', df)

        # Order by with expression support (only field names for now)
        if args.order_by:
            order_exprs = parse_field_expressions(parse_literal_list(args.order_by, "--order-by"))
            order = [expr_to_order_str(e) for e in order_exprs]
            ascending = [not str(col).startswith('-') for col in order]
            cols = [str(col).lstrip('-') for col in order]
            df = df.sort_values(by=cols, ascending=ascending)

        # Limit with cap
        cap = settings.SIEMATIC_SEARCH.get("MAX_ROWS", 10_000)
        n = min(args.limit or cap, cap)
        return df.head(n)

    # ---- Records path ----
    def run_records(self, rows, args, ctx):
        if args.model or args.using:
            raise ValueError("--model/--using are not supported for in-memory datasets")

        def match(row, exprs, include=True):
            for expr in exprs or []:
                f, l, v = parse_lookup(expr)
                val = row.get(f)
                if l == "exact":
                    if (val == v) != include:
                        return False
                elif l == "in":
                    if (val in v) != include:
                        return False
                elif l == "contains":
                    if (v in str(val)) != include:
                        return False
                elif l == "gt":
                    if (val > v) != include:
                        return False
                elif l == "gte":
                    if (val >= v) != include:
                        return False
                elif l == "lt":
                    if (val < v) != include:
                        return False
                elif l == "lte":
                    if (val <= v) != include:
                        return False
                # Add more lookups as needed
            return True

        # Filtering
        filtered = (row for row in rows if match(row, args.filter, include=True))
        # Excluding
        filtered = (row for row in filtered if match(row, args.exclude, include=False))

        # Select (projection) with expression support
        from search2.engine.expression_util import parse_field_expressions, generate_keyword_args, convert_to_python_expression
        if args.select:
            select_exprs = parse_field_expressions(parse_literal_list(args.select, "--select"))
            select_row = handle_select_expressions(select_exprs, 'records')
            filtered = (select_row(row) for row in filtered)

        # Order by with expression support (only field names for now)
        if args.order_by:
            order_exprs = parse_field_expressions(parse_literal_list(args.order_by, "--order-by"))
            order = [expr_to_order_str(e) for e in order_exprs]
            def sort_key(row):
                return tuple((-row.get(str(col).lstrip('-')) if str(col).startswith('-') else row.get(str(col).lstrip('-'))) for col in order)
            filtered = sorted(filtered, key=sort_key)

        # Limit with cap
        cap = settings.SIEMATIC_SEARCH.get("MAX_ROWS", 10_000)
        n = min(args.limit or cap, cap)
        if isinstance(filtered, list):
            return filtered[:n]
        else:
            # If filtered is a generator, use islice for lazy limiting
            from itertools import islice
            return list(islice(filtered, n))
