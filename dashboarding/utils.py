import string
from typing import Dict, Type

def guess_type(format_spec: str) -> Type:
    """
    Guess the expected type based on format specifier.
    """
    if format_spec.endswith('d'):
        return int
    if format_spec.endswith(('f', 'e', 'g')):
        return float
    return str

def format_kwargs_spec(fmt_string: str) -> Dict[str, Type]:
    """
    Parse a format string and return a dict of field names to expected types.
    """
    fmt = string.Formatter()
    result = {}
    for _, name, spec, _ in fmt.parse(fmt_string):
        if name:
            result[name] = guess_type(spec)
    return result