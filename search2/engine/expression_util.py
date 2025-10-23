# Utility functions for parsing and converting search command expressions.
# Adapted from Delve project events/search_commands/qs/_util.py for SIEMatic integration.

import logging
import ast

from django.db.models import F, Value, Q, Func, ExpressionWrapper
from django.db.models.fields.json import KT
from django.db.models import (
    DurationField,
    CharField,
    TextField,
    IntegerField,
    FloatField,
    BooleanField,
    DateField,
    DateTimeField,
    TimeField,
    DecimalField,
)
from django.db.models import (
    Sum,
    Avg,
    Count,
    Max,
    Min,
    StdDev,
    Variance,
)
from django.db.models.functions import (
    Lower,
    Upper,
    Length,
    Trim,
    Cast,
    Coalesce,
    Concat,
    Greatest,
    JSONObject,
    Least,
    LPad,
    RPad,
    LTrim,
    RTrim,
    Substr,
    Replace,
    Reverse,
    Now,
    TruncDate,
    TruncHour,
    TruncMinute,
    TruncMonth,
    TruncSecond,
    TruncYear,
    StrIndex,
    Abs,
    ATan2,
    Ceil,
    Cos,
    Cot,
    Degrees,
    Exp,
    Floor,
    Ln,
    Log,
    Mod,
    Pi,
    Power,
    Radians,
    Round,
    Sign,
    Sin,
    Sqrt,
    Tan,
    Trunc,
    Extract,
    ExtractDay,
    ExtractHour,
    ExtractMinute,
    ExtractMonth,
    ExtractQuarter,
    ExtractSecond,
    ExtractWeek,
    ExtractWeekDay,
    ExtractYear,
)


# Placeholder for cast function. Replace with your own implementation if needed.
def cast(val):
    return val

# Unified registry for supported functions
def _django_lower(field):
    return Lower(field)
def _pandas_lower(series):
    return series.str.lower()
def _python_lower(val):
    return val.lower() if isinstance(val, str) else val

def _django_length(field):
    return Length(field)
def _pandas_length(series):
    return series.str.len()
def _python_length(val):
    return len(val)

SUPPORTED_FUNCTIONS = {
    'ExpressionWrapper': {
        'qs': ExpressionWrapper,
    },
    'Lower': {
        'qs': Lower,
        'df': lambda series: series.str.lower(),
        'records': lambda val: val.lower() if isinstance(val, str) else val,
    },
    'Upper': {
        'qs': Upper,
        'df': lambda series: series.str.upper(),
        'records': lambda val: val.upper() if isinstance(val, str) else val,
    },
    'Length': {
        'qs': Length,
        'df': lambda series: series.str.len(),
        'records': lambda val: len(val),
    },
    'Trim': {
        'qs': Trim,
        'df': lambda series: series.str.strip(),
        'records': lambda val: val.strip() if isinstance(val, str) else val,
    },
    'Value': {
        'qs': Value,
        'df': lambda val: val,
        'records': lambda val: val,
    },
    'Greatest': {
        'qs': Greatest,
    },
    'JSONObject': {
        'qs': JSONObject,
    },
    'Least': {
        'qs': Least,
    },
    'LPad': {
        'qs': LPad,
    },
    'RPad': {
        'qs': RPad,
    },
    'LTrim': {
        'qs': LTrim,
    },
    'RTrim': {
        'qs': RTrim,
    },
    'Substr': {
        'qs': Substr,
    },
    'Replace': {
        'qs': Replace,
    },
    'Reverse': {
        'qs': Reverse,
    },
    'F': {
        'qs': F,
    },
    'Q': {
        'qs': Q,
    },
    'Func': {
        'qs': Func,
    },
    'Now': {
        'qs': Now,
    },
    'TruncDate': {
        'qs': TruncDate,
    },
    'TruncHour': {
        'qs': TruncHour,
    },
    'TruncMinute': {
        'qs': TruncMinute,
    },
    'TruncMonth': {
        'qs': TruncMonth,
    },
    'TruncSecond': {
        'qs': TruncSecond,
    },
    'TruncYear': {
        'qs': TruncYear,
    },
    'StrIndex': {
        'qs': StrIndex,
    },
    'Abs': {
        'qs': Abs,
    },
    'ATan2': {
        'qs': ATan2,
    },
    'Ceil': {
        'qs': Ceil,
    },
    'Cos': {
        'qs': Cos,
    },
    'Cot': {
        'qs': Cot,
    },
    'Degrees': {
        'qs': Degrees,
    },
    'Exp': {
        'qs': Exp,
    },
    'Floor': {
        'qs': Floor,
    },
    'KT': {
        'qs': KT,
    },
    'Ln': {
        'qs': Ln,
    },
    'Log': {
        'qs': Log,
    },
    'Mod': {
        'qs': Mod,
    },
    'Pi': {
        'qs': Pi,
    },
    'Power': {
        'qs': Power,
    },
    'Radians': {
        'qs': Radians,
    },
    'Round': {
        'qs': Round,
    },
    'Sign': {
        'qs': Sign,
    },
    'Sin': {
        'qs': Sin,
    },
    'Sqrt': {
        'qs': Sqrt,
    },
    'Tan': {
        'qs': Tan,
    },
    'Trunc': {
        'qs': Trunc,
    },
    'Extract': {
        'qs': Extract,
    },
    'ExtractDay': {
        'qs': ExtractDay,
    },
    'ExtractHour': {
        'qs': ExtractHour,
    },
    'ExtractMinute': {
        'qs': ExtractMinute,
    },
    'ExtractMonth': {
        'qs': ExtractMonth,
    },
    'ExtractQuarter': {
        'qs': ExtractQuarter,
    },
    'ExtractSecond': {
        'qs': ExtractSecond,
    },
    'ExtractWeek': {
        'qs': ExtractWeek,
    },
    'ExtractWeekDay': {
        'qs': ExtractWeekDay,
    },
    'ExtractYear': {
        'qs': ExtractYear,
    },
    'Sum': {
        'qs': Sum,
        'df': lambda series: series.sum(),
        'records': lambda vals: sum(vals),
    },
    'Avg': {
        'qs': Avg,
        'df': lambda series: series.mean(),
        'records': lambda vals: sum(vals) / len(vals) if vals else None,
    },
    'Count': {
        'qs': Count,
        'df': lambda series: series.count(),
        'records': lambda vals: len(vals),
    },
    'Max': {
        'qs': Max,
        'df': lambda series: series.max(),
        'records': lambda vals: max(vals) if vals else None,
    },
    'Min': {
        'qs': Min,
        'df': lambda series: series.min(),
        'records': lambda vals: min(vals) if vals else None,
    },
    'StdDev': {
        'qs': StdDev,
    },
    'Variance': {
        'qs': Variance,
    },
}

FIELD_CLASSES = {
    'CharField': {
        'qs': CharField,
        'df': str,
        'records': str,
    },
    'TextField': {
        'qs': TextField,
        'df': str,
        'records': str,
    },
    'IntegerField': {
        'qs': IntegerField,
        'df': int,
        'records': int,
    },
    'FloatField': {
        'qs': FloatField,
        'df': float,
        'records': float,
    },
    'BooleanField': {
        'qs': BooleanField,
        'df': bool,
        'records': bool,
    },
    'DateField': {
        'qs': DateField
    },
    'DateTimeField': {
        'qs': DateTimeField
    },
    'TimeField': {
        'qs': TimeField
    },
    'DecimalField': {
        'qs': DecimalField
    },
    'DurationField': {
        'qs': DurationField
    },
}

def evaluate_node(node):
    if isinstance(node, list):
        return [evaluate_node(n) for n in node]
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Unsupported function type in expression")
        func_name = node.func.id
        args = [evaluate_node(arg) for arg in node.args]
        kwargs = {kw.arg: evaluate_node(kw.value) for kw in node.keywords}
        return func_name, args, kwargs
    elif isinstance(node, ast.Assign):
        if not isinstance(node.targets[0], ast.Name):
            raise ValueError("Unsupported assignment target in expression")
        target = node.targets[0].id
        value = evaluate_node(node.value)
        return {target: value}
    elif isinstance(node, ast.Expr):
        return evaluate_node(node.value)
    elif isinstance(node, ast.Constant):
        return node.value
    elif isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        attr = f"{evaluate_node(node.value)}__{node.attr}"
        return attr
    elif isinstance(node, ast.BinOp):
        left = evaluate_node(node.left)
        right = evaluate_node(node.right)
        op = node.op
        return ('BinOp', left, op, right)
    elif isinstance(node, ast.UnaryOp):
        operand = evaluate_node(node.operand)
        op = node.op
        return ('UnaryOp', operand, op)
    else:
        raise ValueError(f"Unsupported AST node type: {type(node)}")

def parse_field_expressions(field_expressions):
    parsed_expressions = []
    for expr in field_expressions:
        try:
            tree = ast.parse(expr, mode='single')
            parsed_expressions.extend(evaluate_node(tree.body))
        except SyntaxError as e:
            raise
    return parsed_expressions

def parse_function_args(func_name, func_args):
    args = []
    kwargs = {}
    for arg in func_args:
        if '=' in arg:
            key, value = arg.split('=', 1)
            key = key.strip()
            value = value.strip()
            kwargs[key] = value
        else:
            args.append(arg.strip())
    return args, kwargs

def generate_keyword_args(parsed_expressions):
    keyword_args = {}
    positional_args = []
    for expr in parsed_expressions:
        if isinstance(expr, dict):
            keyword_args.update(convert_to_django_expression(expr))
        else:
            positional_args.append(convert_to_django_expression(expr))

    return positional_args, keyword_args


def convert_to_django_expression(expr):
    import ast
    if isinstance(expr, tuple) and expr[0] == 'BinOp':
        _, left, op, right = expr
        left_expr = convert_to_django_expression(left)
        right_expr = convert_to_django_expression(right)
        if isinstance(op, ast.Add):
            return left_expr + right_expr
        elif isinstance(op, ast.Sub):
            return left_expr - right_expr
        elif isinstance(op, ast.Mult):
            return left_expr * right_expr
        elif isinstance(op, ast.Div):
            return left_expr / right_expr
        elif isinstance(op, ast.Mod):
            return left_expr % right_expr
        elif isinstance(op, ast.Pow):
            return left_expr ** right_expr
        elif isinstance(op, ast.BitOr):
            return left_expr | right_expr
        elif isinstance(op, ast.BitAnd):
            return left_expr & right_expr
        elif isinstance(op, ast.BitXor):
            return left_expr & right_expr
        else:
            raise ValueError(f"Unsupported binary operator: {type(op)}")
    elif isinstance(expr, tuple) and expr[0] == 'UnaryOp':
        _, operand, op = expr
        operand_expr = convert_to_django_expression(operand)
        if isinstance(op, ast.USub):
            return -operand_expr
        elif isinstance(op, ast.Invert):
            return ~operand_expr
        else:
            raise ValueError(f"Unsupported unary operator: {type(op)}")
    elif isinstance(expr, tuple):
        func_name, args, kwargs = expr
        args = [convert_to_django_expression(arg) for arg in args]
        kwargs = {key: convert_to_django_expression(value) for key, value in kwargs.items()}
        func_entry = SUPPORTED_FUNCTIONS.get(func_name)
        if func_entry and 'qs' in func_entry:
            if func_name == 'Avg' and 'output_field' not in kwargs:
                kwargs['output_field'] = FloatField()
            return func_entry['qs'](*args, **kwargs)
        else:
            raise ValueError(f"Function {func_name} is not supported for QuerySet")
    elif isinstance(expr, str):
        if expr in FIELD_CLASSES and 'qs' in FIELD_CLASSES[expr]:
            return FIELD_CLASSES[expr]['qs']()
        else:
            return cast(expr.strip())
    elif isinstance(expr, dict):
        return {key: convert_to_django_expression(value) for key, value in expr.items()}
    else:
        return expr

# Integration layer for DataFrame and records
def convert_to_pandas_expression(expr):
    """
    Convert parsed expression to Pandas operation.
    Only a few functions are supported for now.
    """
    if isinstance(expr, tuple) and expr[0] == 'BinOp':
        _, left, op, right = expr
        left_expr = convert_to_pandas_expression(left)
        right_expr = convert_to_pandas_expression(right)
        if isinstance(op, ast.Add):
            return left_expr + right_expr
        elif isinstance(op, ast.Sub):
            return left_expr - right_expr
        elif isinstance(op, ast.Mult):
            return left_expr * right_expr
        elif isinstance(op, ast.Div):
            return left_expr / right_expr
        elif isinstance(op, ast.Mod):
            return left_expr % right_expr
        else:
            raise ValueError(f"Unsupported binary operator for pandas: {type(op)}")
    elif isinstance(expr, tuple) and expr[0] == 'UnaryOp':
        _, operand, op = expr
        operand_expr = convert_to_pandas_expression(operand)
        if isinstance(op, ast.USub):
            return -operand_expr
        else:
            raise ValueError(f"Unsupported unary operator for pandas: {type(op)}")
    elif isinstance(expr, tuple):
        func_name, args, kwargs = expr
        args = [convert_to_pandas_expression(arg) for arg in args]
        kwargs = {key: convert_to_pandas_expression(value) for key, value in kwargs.items()}
        func_entry = SUPPORTED_FUNCTIONS.get(func_name)
        if func_entry and 'df' in func_entry:
            return func_entry['df'](*args, **kwargs)
        else:
            raise ValueError(f"Function {func_name} is not supported for DataFrame")
    elif isinstance(expr, str):
        # For DataFrame, assume expr is a column name
        return expr
    elif isinstance(expr, dict):
        return {key: convert_to_pandas_expression(value) for key, value in expr.items()}
    else:
        return expr

def convert_to_python_expression(expr):
    """
    Convert parsed expression to Python-native operation (for list[dict] records).
    Only a few functions are supported for now.
    """
    if isinstance(expr, tuple) and expr[0] == 'BinOp':
        _, left, op, right = expr
        left_expr = convert_to_python_expression(left)
        right_expr = convert_to_python_expression(right)
        if isinstance(op, ast.Add):
            return left_expr + right_expr
        elif isinstance(op, ast.Sub):
            return left_expr - right_expr
        elif isinstance(op, ast.Mult):
            return left_expr * right_expr
        elif isinstance(op, ast.Div):
            return left_expr / right_expr
        elif isinstance(op, ast.Mod):
            return left_expr % right_expr
        else:
            raise ValueError(f"Unsupported binary operator for records: {type(op)}")
    elif isinstance(expr, tuple) and expr[0] == 'UnaryOp':
        _, operand, op = expr
        operand_expr = convert_to_python_expression(operand)
        if isinstance(op, ast.USub):
            return -operand_expr
        else:
            raise ValueError(f"Unsupported unary operator for records: {type(op)}")
    elif isinstance(expr, tuple):
        func_name, args, kwargs = expr
        args = [convert_to_python_expression(arg) for arg in args]
        kwargs = {key: convert_to_python_expression(value) for key, value in kwargs.items()}
        func_entry = SUPPORTED_FUNCTIONS.get(func_name)
        if func_entry and 'records' in func_entry:
            return func_entry['records'](*args, **kwargs)
        else:
            raise ValueError(f"Function {func_name} is not supported for records")
    elif isinstance(expr, str):
        return expr
    elif isinstance(expr, dict):
        return {key: convert_to_python_expression(value) for key, value in expr.items()}
    else:
        return expr
