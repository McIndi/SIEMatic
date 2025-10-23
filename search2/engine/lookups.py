from typing import Any, Dict, List, Tuple
from django.conf import settings
from .literals import parse_literal

def parse_lookup(expr: str) -> Tuple[str, str, Any]:
    # expr: 'lhs=value' where lhs may end with a lookup (e.g., field__icontains)
    if "=" not in expr:
        raise ValueError(f"Invalid filter '{expr}', expected field__lookup=value")
    lhs, raw_val = expr.split("=", 1)
    parts = lhs.split("__")
    allowed = settings.SIEMATIC_SEARCH.get("ALLOWED_LOOKUPS", set())
    if parts[-1] in allowed:
        lookup = parts[-1]
        field_path = "__".join(parts[:-1])
    else:
        lookup = "exact"
        field_path = lhs
    val = parse_literal(raw_val, "--filter/--exclude")
    if lookup == "in" and not isinstance(val, (list, tuple, set)):
        val = [val]
    if lookup == "range":
        if not (isinstance(val, (list, tuple)) and len(val) == 2):
            raise ValueError("range expects a 2-tuple/list literal, e.g. ts__range=(a,b)")
        val = (val[0], val[1])
    return field_path, lookup, val

def get_nested(value: Any, path_parts: List[str]) -> Any:
    cur = value
    for part in path_parts:
        if cur is None: return None
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif hasattr(cur, part):
            cur = getattr(cur, part)
        else:
            return None
    return cur

def matches(record: Dict[str, Any], field_path: str, lookup: str, val: Any) -> bool:
    parts = field_path.split("__") if field_path else []
    v = get_nested(record, parts) if parts else record
    if lookup == "exact":     return v == val
    if lookup == "iexact":    return str(v).lower() == str(val).lower()
    if lookup == "contains":  return str(val) in str(v)
    if lookup == "icontains": return str(val).lower() in str(v).lower()
    if lookup == "startswith":  return str(v).startswith(str(val))
    if lookup == "istartswith": return str(v).lower().startswith(str(val).lower())
    if lookup == "endswith":    return str(v).endswith(str(val))
    if lookup == "iendswith":   return str(v).lower().endswith(str(val).lower())
    if lookup == "gt":        return v is not None and v > val
    if lookup == "gte":       return v is not None and v >= val
    if lookup == "lt":        return v is not None and v < val
    if lookup == "lte":       return v is not None and v <= val
    if lookup == "in":        return v in set(val)
    if lookup == "range":
        lo, hi = val
        try:    return (v is not None) and (v >= lo) and (v <= hi)
        except Exception: return False
    raise ValueError(f"Unsupported lookup: {lookup}")
