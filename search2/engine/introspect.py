from typing import Iterable, Set

def related_models_from_paths(base_model, paths: Iterable[str]) -> Set[type]:
    rels: set[type] = set()
    for path in paths:
        parts = [p for p in path.split("__") if p]
        cur = base_model
        for part in parts:
            try:
                field = cur._meta.get_field(part)
            except Exception:
                break  # not a declared field → stop (JSON subkey or invalid)
            rel_model = getattr(field, "related_model", None)
            if not rel_model:
                break
            rels.add(rel_model)
            cur = rel_model
    return rels
