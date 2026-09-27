from django.core.management.base import BaseCommand
from django.utils import timezone

from engagement.models import Enquiry


class Command(BaseCommand):
    help = 'Delete enquiries past their retention date (run daily from cron).'

    def handle(self, *args, **options):
        count, _ = Enquiry.objects.filter(retention_until__lt=timezone.now().date()).delete()
        self.stdout.write(f'Deleted {count} expired enquiries.')
