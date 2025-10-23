from textwrap import dedent


class AnnotateCmd:
    """Annotate command for adding calculated fields.
    Examples:
        annotate --set='avg_duration=Avg("duration")' --set='lower_host=Lower("host")'
    """
    name = "annotate"

    def add_arguments(self, p):
        p.add_argument(
            "--set",
            action="append",
            default=[],
            help=dedent("""
            Set field to expression (e.g., --set='new_field=Func(arg)'), 
            can be used multiple times.
            Supports placeholders ${fieldname}.
            """),
        )

    def run_none(self, data, args, ctx):
        raise NotImplementedError("annotate command requires input data")

    def run_qs(self, qs, args, ctx):
        from search2.engine.expression_util import parse_field_expressions, generate_keyword_args
        sets = getattr(args, 'set', [])
        exprs = []
        for item in sets:
            if '=' not in item:
                continue
            field, expr = item.split('=', 1)
            exprs.append(f'{field.strip()}={expr.strip()}')
        parsed = parse_field_expressions(exprs)
        _, annotations = generate_keyword_args(parsed)
        if annotations:
            return qs.annotate(**annotations)
        return qs

    def run_df(self, df, args, ctx):
        from search2.engine.expression_util import parse_field_expressions, generate_keyword_args, convert_to_pandas_expression
        sets = getattr(args, 'set', [])
        exprs = []
        for item in sets:
            if '=' not in item:
                continue
            field, expr = item.split('=', 1)
            exprs.append(f'{field.strip()}={expr.strip()}')
        parsed = parse_field_expressions(exprs)
        _, annotations = generate_keyword_args(parsed)
        for field, expr in annotations.items():
            df[field] = convert_to_pandas_expression(expr)
        return df

    def run_records(self, rows, args, ctx):
        from search2.engine.expression_util import parse_field_expressions, generate_keyword_args, convert_to_python_expression
        sets = getattr(args, 'set', [])
        exprs = []
        for item in sets:
            if '=' not in item:
                continue
            field, expr = item.split('=', 1)
            exprs.append(f'{field.strip()}={expr.strip()}')
        parsed = parse_field_expressions(exprs)
        _, annotations = generate_keyword_args(parsed)
        result = []
        for row in rows:
            new_row = row.copy()
            for field, expr in annotations.items():
                new_row[field] = convert_to_python_expression(expr)
            result.append(new_row)
        return result
