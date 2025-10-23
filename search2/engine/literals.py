import ast

def parse_literal(expr: str, flagname: str):
    try:
        return ast.literal_eval(expr)
    except Exception:
        # Accept unquoted strings as valid string values
        expr_strip = expr.strip()
        # Handle special cases for None, True, False
        if expr_strip.lower() == "none":
            return None
        if expr_strip.lower() == "true":
            return True
        if expr_strip.lower() == "false":
            return False
        return expr_strip

def parse_literal_list(expr: str, flagname: str) -> list:
    try:
        val = ast.literal_eval(expr)
    except (ValueError, SyntaxError):
        raise ValueError(f"{flagname} must be a valid list/tuple literal")
    if not isinstance(val, (list, tuple)):
        raise ValueError(f"{flagname} must be a list/tuple literal, got {type(val)}")
    return list(val)
