from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from project.signals import AGENT_GROUP_NAME, REGISTERED_GROUP_NAME


class Command(BaseCommand):
    help = 'Fail if a shipper user can also read the audit trail.'

    def handle(self, *args, **options):
        unsafe = list(
            get_user_model().objects.filter(
                groups__name=AGENT_GROUP_NAME,
            ).filter(
                groups__name=REGISTERED_GROUP_NAME,
            ).values_list('username', flat=True)
        )
        if unsafe:
            raise CommandError(
                'Shipper users must not belong to Registered User: '
                + ', '.join(sorted(unsafe))
            )
        self.stdout.write(self.style.SUCCESS('All Agent users are write-only.'))
