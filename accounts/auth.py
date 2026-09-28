"""Roles, the session authentication used by auth/, manage/ and write/, and
the permission classes that enforce the two realms."""

import secrets
import string

from django.contrib.auth.models import Group
from django.http import HttpResponse, JsonResponse
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission

from .models import ADMINS, PUBLISHERS, Profile, Realm

ROLE_GROUPS = {Realm.ADMIN: ADMINS, Realm.PUBLISHER: PUBLISHERS}


def role_of(user):
    """'admin', 'publisher' or None. Superusers count as admins."""
    if not user or not user.is_authenticated:
        return None
    cached = getattr(user, '_mumita_role', 'unset')
    if cached != 'unset':
        return cached
    names = set(user.groups.values_list('name', flat=True))
    if user.is_superuser or ADMINS in names:
        role = Realm.ADMIN.value
    elif PUBLISHERS in names:
        role = Realm.PUBLISHER.value
    else:
        role = None
    user._mumita_role = role
    return role


def set_role(user, role):
    """Put the user in exactly one realm group. Admins are also staff and
    superusers, so they can use the Django admin for the rest of the CMS."""
    user.groups.remove(*Group.objects.filter(name__in=ROLE_GROUPS.values()))
    group, _ = Group.objects.get_or_create(name=ROLE_GROUPS[role])
    user.groups.add(group)
    is_admin = role == Realm.ADMIN
    user.is_staff = is_admin
    user.is_superuser = is_admin
    user.save(update_fields=['is_staff', 'is_superuser'])
    user._mumita_role = Realm(role).value


def profile_of(user):
    profile, _ = Profile.objects.get_or_create(
        user=user, defaults={'name': user.get_full_name() or user.get_username(), 'must_change_password': False}
    )
    return profile


def display_name(user):
    if not user:
        return ''
    try:
        return user.profile.name or user.get_username()
    except Profile.DoesNotExist:
        return user.get_full_name() or user.get_username()


def generate_password(length=24):
    """A random password of letters, digits and a few symbols (24 chars,
    about 150 bits). Always contains each character class."""
    alphabet = string.ascii_letters + string.digits + '-_.!@#%'
    while True:
        value = ''.join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in value) and any(c.isupper() for c in value)
                and any(c.isdigit() for c in value) and any(not c.isalnum() for c in value)):
            return value


class DashboardSessionAuthentication(SessionAuthentication):
    """Django session auth with CSRF enforced (DRF's default), and a
    WWW-Authenticate value so a missing session answers 401, not 403."""

    def authenticate_header(self, request):
        return 'Session'


class _RealmPermission(BasePermission):
    roles = ()

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_active):
            return False
        if role_of(user) not in self.roles:
            return False
        if profile_of(user).must_change_password:
            raise PermissionDenied('password_change_required')
        return True


class IsAdmin(_RealmPermission):
    roles = (Realm.ADMIN.value,)


class IsWriter(_RealmPermission):
    """Publishers and admins (the write/ API)."""

    roles = (Realm.ADMIN.value, Realm.PUBLISHER.value)


def lockout_response(request, original_response=None, credentials=None):
    """django-axes lock-out: JSON 429 for the API, plain text elsewhere."""
    if request.path.startswith('/api/'):
        return JsonResponse({'detail': 'locked'}, status=429)
    return HttpResponse(
        'Too many failed sign-in attempts. Try again in an hour.', status=429, content_type='text/plain'
    )
