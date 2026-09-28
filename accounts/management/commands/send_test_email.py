from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from common.mail import send_email


class Command(BaseCommand):
    help = 'Send a test email through the configured mail settings.'

    def add_arguments(self, parser):
        parser.add_argument('address', nargs='?', help='Recipient address.')
        parser.add_argument('--to', help='Recipient address (same as the positional argument).')

    def handle(self, *args, address=None, to=None, **options):
        to = address or to
        if not to:
            raise CommandError('Give a recipient: send_test_email you@example.com')
        backend = settings.MAILERS['default']['BACKEND'].rsplit('.', 1)[-1]
        self.stdout.write(f'Sending from {settings.DEFAULT_FROM_EMAIL} via {backend}...')
        if not send_email([to], 'Mumita Holdings: test email', 'test'):
            raise CommandError('Sending failed; see the log above.')
        self.stdout.write(self.style.SUCCESS('Sent.'))
