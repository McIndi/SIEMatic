"""
Signals for user creation and default group assignment in SIEMatic.
"""
from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.apps import apps

CustomUser = apps.get_model(settings.AUTH_USER_MODEL.split('.')[0], settings.AUTH_USER_MODEL.split('.')[1])

REGISTERED_GROUP_NAME = "Registered User"

@receiver(post_save, sender=CustomUser)
def add_user_to_registered_group(sender, instance, created, **kwargs):
    if not created:
        return
    group, _ = Group.objects.get_or_create(name=REGISTERED_GROUP_NAME)
    # Example permissions: view_event, view_dashboard, search_event
    # Add your actual permission codenames here
    permission_codenames = [
        "view_event",
        "view_dashboard",
        "view_panel",
        "view_finding",
        "view_savedsearch",
    ]
    for codename in permission_codenames:
        perm = Permission.objects.filter(codename=codename).first()
        if perm and perm not in group.permissions.all():
            group.permissions.add(perm)
    if group not in instance.groups.all():
        instance.groups.add(group)
