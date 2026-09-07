from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from project.signals import AGENT_GROUP_NAME


class Command(BaseCommand):
    help = 'Fail if a shipper user can also read the audit trail.'

    def handle(self, *args, **options):
        shippers = get_user_model().objects.filter(
            groups__name=AGENT_GROUP_NAME,
        ).distinct()
        unsafe = [
            user.username
            for user in shippers
            if user.has_perm('events.view_event')
        ]
        if unsafe:
            raise CommandError(
                'Shipper users must not be able to view events: '
                + ', '.join(sorted(unsafe))
            )
        self.stdout.write(self.style.SUCCESS('All Agent users are write-only.'))
