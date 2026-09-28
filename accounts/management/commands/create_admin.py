"""First deploy: create the first dashboard admin.

    python manage.py create_admin --email name@mumitaholdings.com --name "Full Name"

A random password is generated and printed ONCE to this console. It is not
stored anywhere else and not emailed. The admin must change it at first
sign-in (mumitaholdings.com/dashboard/login).
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.auth import generate_password, set_role
from accounts.models import Profile, Realm


class Command(BaseCommand):
    help = 'Create a dashboard admin with a generated password, printed once.'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True)
        parser.add_argument('--name', required=True)

    def handle(self, *args, email, name, **options):
        User = get_user_model()
        email = email.strip().lower()
        domain = settings.ACCOUNT_EMAIL_DOMAIN
        if email.rsplit('@', 1)[-1] != domain or email.count('@') != 1:
            raise CommandError(f'The email must end in @{domain}.')
        if User.objects.filter(username=email).exists():
            raise CommandError('An account with this email already exists. Use the dashboard to reset its password.')
        password = generate_password()
        with transaction.atomic():
            user = User.objects.create_user(username=email, email=email, password=password)
            Profile.objects.create(user=user, name=name.strip(), must_change_password=True)
            set_role(user, Realm.ADMIN)
        self.stdout.write(self.style.SUCCESS(f'Admin {email} created.'))
        self.stdout.write('Temporary password (shown once, not stored anywhere else):')
        self.stdout.write(f'    {password}')
        self.stdout.write('Sign in at /dashboard/login and choose a new password.')
