"""Dashboard accounts (PLATFORM-CONTRACT "Accounts and logins").

One Django user table, two realms, told apart by group:
`admins` (the dashboard) and `publishers` (the article editor).
The username is the email address, lower-cased.
"""

from django.conf import settings
from django.db import models

ADMINS = 'admins'
PUBLISHERS = 'publishers'


class Realm(models.TextChoices):
    ADMIN = 'admin', 'Admin'
    PUBLISHER = 'publisher', 'Publisher'


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    name = models.CharField(max_length=120, help_text='Display name, used as the article byline.')
    must_change_password = models.BooleanField(
        default=True, help_text='Set for new accounts and after a reset; cleared by a password change.'
    )

    def __str__(self):
        return self.name or self.user.get_username()


class LoginEvent(models.Model):
    """Every sign-in attempt through the API, successful or not.

    No IP address is stored, only a keyed hash (the same scheme as
    enquiries), and only the browser family of the user agent."""

    class Outcome(models.TextChoices):
        SUCCESS = 'success', 'Signed in'
        BAD_CREDENTIALS = 'bad_credentials', 'Wrong email or password'
        WRONG_REALM = 'wrong_realm', 'Right password, wrong sign-in page'
        INACTIVE = 'inactive', 'Account deactivated'
        LOCKED = 'locked', 'Locked out'

    created = models.DateTimeField(auto_now_add=True, db_index=True)
    realm = models.CharField(max_length=10, choices=Realm.choices, blank=True)
    username = models.CharField(max_length=254, help_text='The email address tried.')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='login_events'
    )
    success = models.BooleanField(default=False, db_index=True)
    outcome = models.CharField(max_length=20, choices=Outcome.choices)
    ip_hash = models.CharField(max_length=64, blank=True)
    user_agent_family = models.CharField(max_length=60, blank=True)

    class Meta:
        ordering = ['-created', '-pk']

    def __str__(self):
        return f'{self.username} {self.outcome} {self.created:%Y-%m-%d %H:%M}'
