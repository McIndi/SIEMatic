from django.core.exceptions import PermissionDenied

PIPELINE_DENIED_MODELS = {
    "project.customuser",
    "search2.savedsearch",
}


def _has_view_perm(user, model):
    return user.has_perm(f"{model._meta.app_label}.view_{model._meta.model_name}")


def _check_model_allowed(model):
    if model._meta.label_lower in PIPELINE_DENIED_MODELS:
        raise PermissionDenied(
            f"{model._meta.label} cannot be queried through the search pipeline."
        )


def default_check(request, base_model, related_models):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        raise PermissionDenied("Authentication required.")
    _check_model_allowed(base_model)
    if not _has_view_perm(user, base_model):
        raise PermissionDenied(f"No permission to view {base_model._meta.label}")
    for m in related_models:
        _check_model_allowed(m)
        if not _has_view_perm(user, m):
            raise PermissionDenied(f"No permission to traverse related model {m._meta.label}")

def get_authz_check():
    from django.conf import settings
    path = settings.SIEMATIC_SEARCH.get("AUTHZ_CHECK", "siematic.search.engine.authz.default_check")
    mod, fn = path.rsplit(".", 1)
    import importlib
    return getattr(importlib.import_module(mod), fn)
