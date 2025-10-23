from django.core.exceptions import PermissionDenied

def _has_view_perm(user, model):
    return user.has_perm(f"{model._meta.app_label}.view_{model._meta.model_name}")

def default_check(request, base_model, related_models):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        raise PermissionDenied("Authentication required.")
    if not _has_view_perm(user, base_model):
        raise PermissionDenied(f"No permission to view {base_model._meta.label}")
    for m in related_models:
        if not _has_view_perm(user, m):
            raise PermissionDenied(f"No permission to traverse related model {m._meta.label}")

def get_authz_check():
    from django.conf import settings
    path = settings.SIEMATIC_SEARCH.get("AUTHZ_CHECK", "siematic.search.engine.authz.default_check")
    mod, fn = path.rsplit(".", 1)
    import importlib
    return getattr(importlib.import_module(mod), fn)
