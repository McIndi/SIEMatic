from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from agent.models import BatchReceipt


class Command(BaseCommand):
    help = 'Delete expired batch receipts after the configured replay window.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=30)

    def handle(self, *args, **options):
        days = options['days']
        if days < 1:
            raise CommandError('--days must be at least 1')
        cutoff = timezone.now() - timedelta(days=days)
        deleted, _ = BatchReceipt.objects.filter(created__lt=cutoff).delete()
        self.stdout.write(self.style.SUCCESS(f'Deleted {deleted} expired batch receipts.'))
