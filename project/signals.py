"""
Signals for default group setup and user group assignment in SIEMatic.
"""
import logging

from django.apps import apps as django_apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.management import create_permissions
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

REGISTERED_GROUP_NAME = "Registered User"
AGENT_GROUP_NAME = "Agent"
DEFAULT_PERMISSIONS = [
    ("events", "event", "view_event"),
    ("dashboarding", "dashboard", "view_dashboard"),
    ("dashboarding", "panel", "view_panel"),
    ("crawlers", "finding", "view_finding"),
    ("search2", "savedsearch", "view_savedsearch"),
]
AGENT_PERMISSIONS = [
    ("events", "event", "add_event"),
]


def _resolve_permission(app_label, model, codename):
    content_type = ContentType.objects.get_by_natural_key(app_label, model)
    return Permission.objects.get(content_type=content_type, codename=codename)


def _set_group_permissions(group_name, permission_specs, *, log_missing):
    group, _ = Group.objects.get_or_create(name=group_name)
    permissions = []
    missing_permissions = []

    for app_label, model, codename in permission_specs:
        try:
            permissions.append(_resolve_permission(app_label, model, codename))
        except (ContentType.DoesNotExist, Permission.DoesNotExist):
            missing_permissions.append(f"{app_label}.{model}.{codename}")

    if missing_permissions:
        if log_missing:
            logger.error(
                "Unable to configure %s group; missing permissions: %s",
                group_name,
                ", ".join(missing_permissions),
            )
        return group

    group.permissions.set(permissions)
    return group


def configure_default_groups(*, log_missing):
    _set_group_permissions(
        REGISTERED_GROUP_NAME,
        DEFAULT_PERMISSIONS,
        log_missing=log_missing,
    )
    _set_group_permissions(
        AGENT_GROUP_NAME,
        AGENT_PERMISSIONS,
        log_missing=log_missing,
    )


@receiver(post_migrate, dispatch_uid="project.configure_default_groups")
def configure_groups_after_migrate(sender, app_config, verbosity, **kwargs):
    if app_config.label != "crawlers":
        return

    for target_app in ("events", "dashboarding", "crawlers", "search2"):
        create_permissions(
            django_apps.get_app_config(target_app),
            verbosity=verbosity,
            apps=django_apps,
        )

    configure_default_groups(log_missing=True)


@receiver(post_save, sender=get_user_model(), dispatch_uid="project.add_user_to_registered_group")
def add_user_to_registered_group(sender, instance, created, **kwargs):
    if not created:
        return

    group = Group.objects.filter(name=REGISTERED_GROUP_NAME).first()
    if group is None:
        configure_default_groups(log_missing=False)
        group = Group.objects.get(name=REGISTERED_GROUP_NAME)

    instance.groups.add(group)
