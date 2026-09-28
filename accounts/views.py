"""auth/ (sign-in for both realms), manage/users/ and manage/login-events/."""

import logging

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.mail import send_email
from common.pagination import DashboardPagination
from common.security import ClientIPScopedRateThrottle, client_ip, hash_ip, user_agent_family

from .auth import (
    DashboardSessionAuthentication, IsAdmin, display_name, generate_password, profile_of, role_of, set_role,
)
from .models import ADMINS, PUBLISHERS, LoginEvent, Profile, Realm

logger = logging.getLogger('accounts')
User = get_user_model()

GENERIC_LOGIN_ERROR = 'Invalid email or password.'


def me_payload(user):
    return {
        'id': user.pk,
        'name': display_name(user),
        'email': user.email,
        'role': role_of(user),
        'must_change_password': profile_of(user).must_change_password,
    }


class CsrfEnforcedAPIView(APIView):
    """Auth endpoints use the session, so CSRF applies even before sign-in
    (login CSRF). DRF only enforces it for authenticated sessions, so the
    check is made here for every unsafe method."""

    authentication_classes = [DashboardSessionAuthentication]

    def initial(self, request, *args, **kwargs):
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            DashboardSessionAuthentication().enforce_csrf(request)
        super().initial(request, *args, **kwargs)


@method_decorator(ensure_csrf_cookie, name='dispatch')
class CsrfView(APIView):
    """GET auth/csrf/: sets the csrftoken cookie. The token is also in the
    body, for development where the API is on another host."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        response = Response({'ok': True, 'csrfToken': get_token(request)})
        response['Cache-Control'] = 'no-store'
        return response


class LoginSerializer(serializers.Serializer):
    email = serializers.CharField(max_length=254)
    password = serializers.CharField(max_length=256, trim_whitespace=False)
    realm = serializers.ChoiceField(choices=Realm.choices)


class LoginView(CsrfEnforcedAPIView):
    """POST auth/login/ {email, password, realm}.

    Wrong password, unknown email, deactivated account and wrong realm all
    answer the same 400, so the endpoint reveals nothing. Every attempt is a
    LoginEvent; django-axes counts failures and answers 429 when locked."""

    permission_classes = [AllowAny]
    throttle_classes = [ClientIPScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'detail': GENERIC_LOGIN_ERROR}, status=status.HTTP_400_BAD_REQUEST)
        email = serializer.validated_data['email'].strip().lower()
        password = serializer.validated_data['password']
        realm = serializer.validated_data['realm']
        django_request = request._request

        event = LoginEvent(
            realm=realm, username=email[:254],
            ip_hash=hash_ip(client_ip(request)),
            user_agent_family=user_agent_family(request.headers.get('User-Agent', ''))[:60],
        )
        user = authenticate(django_request, username=email, password=password)

        if getattr(django_request, 'axes_locked_out', False):
            event.outcome = LoginEvent.Outcome.LOCKED
            event.user = User.objects.filter(username=email).first()
            event.save()
            # AxesMiddleware replaces this with the lock-out response (429).
            return Response({'detail': 'locked'}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        if user is None:
            existing = User.objects.filter(username=email).first()
            event.user = existing
            event.outcome = (
                LoginEvent.Outcome.INACTIVE if existing and not existing.is_active and existing.check_password(password)
                else LoginEvent.Outcome.BAD_CREDENTIALS
            )
            event.save()
            return Response({'detail': GENERIC_LOGIN_ERROR}, status=status.HTTP_400_BAD_REQUEST)

        if role_of(user) != realm:
            # Right password, wrong sign-in page. Same answer as a bad password.
            event.user = user
            event.outcome = LoginEvent.Outcome.WRONG_REALM
            event.save()
            return Response({'detail': GENERIC_LOGIN_ERROR}, status=status.HTTP_400_BAD_REQUEST)

        login(django_request, user)
        event.user = user
        event.success = True
        event.outcome = LoginEvent.Outcome.SUCCESS
        event.save()
        return Response({'user': me_payload(user)})


class LogoutView(CsrfEnforcedAPIView):
    permission_classes = [AllowAny]

    def post(self, request):
        logout(request._request)
        return Response({'ok': True})


class MeView(APIView):
    authentication_classes = [DashboardSessionAuthentication]
    permission_classes = [AllowAny]

    def get(self, request):
        user = request.user
        if not (user and user.is_authenticated and user.is_active and role_of(user)):
            return Response({'detail': 'Not signed in.'}, status=status.HTTP_401_UNAUTHORIZED)
        response = Response(me_payload(user))
        response['Cache-Control'] = 'no-store'
        return response


class PasswordView(CsrfEnforcedAPIView):
    """POST auth/password/ {current, new}. Clears must_change_password and
    keeps the current session signed in."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        current = request.data.get('current') or ''
        new = request.data.get('new') or ''
        if not isinstance(current, str) or not user.check_password(current):
            return Response({'current': ['The current password is not correct.']}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(new, str) or not new:
            return Response({'new': ['Enter a new password.']}, status=status.HTTP_400_BAD_REQUEST)
        if new == current:
            return Response({'new': ['Choose a password different from the current one.']}, status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_password(new, user)
        except DjangoValidationError as exc:
            return Response({'new': list(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(new)
        user.save(update_fields=['password'])
        profile = profile_of(user)
        profile.must_change_password = False
        profile.save(update_fields=['must_change_password'])
        update_session_auth_hash(request._request, user)
        return Response({'ok': True, 'user': me_payload(user)})


# --- manage/users/ ---------------------------------------------------------

def login_url(role):
    return f"{settings.FRONTEND_URL}/{'dashboard' if role == Realm.ADMIN else 'write'}/login"


def email_credentials(user, password, *, reset=False):
    role = role_of(user)
    area = 'dashboard' if role == Realm.ADMIN else 'article editor'
    subject = 'Your Mumita Holdings password was reset' if reset else 'Your Mumita Holdings account'
    return send_email(
        [user.email], subject, 'credentials',
        {'name': display_name(user), 'email': user.email, 'password': password, 'area': area,
         'login_url': login_url(role), 'reset': reset},
    )


ADMIN_Q = Q(is_superuser=True) | Q(groups__name=ADMINS)
PUBLISHER_Q = Q(groups__name=PUBLISHERS)


def active_admins():
    return User.objects.filter(pk__in=User.objects.filter(ADMIN_Q, is_active=True).values('pk'))


def admin_emails():
    return sorted({u.email for u in active_admins() if u.email})


class UserSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()
    active = serializers.BooleanField(source='is_active', read_only=True)
    must_change_password = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'name', 'email', 'role', 'active', 'must_change_password', 'last_login', 'date_joined']

    def get_name(self, obj):
        return display_name(obj)

    def get_role(self, obj):
        return role_of(obj)

    def get_must_change_password(self, obj):
        return profile_of(obj).must_change_password


class UserCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    email = serializers.EmailField(max_length=254)
    role = serializers.ChoiceField(choices=Realm.choices)
    password = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False, max_length=256)
    generate = serializers.BooleanField(required=False, default=False)

    def validate_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError('Enter the person\'s name.')
        return value

    def validate_email(self, value):
        value = value.strip().lower()
        domain = settings.ACCOUNT_EMAIL_DOMAIN
        if value.rsplit('@', 1)[-1] != domain:
            raise serializers.ValidationError(f'The email must end in @{domain}.')
        if User.objects.filter(username=value).exists() or User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return value

    def validate(self, attrs):
        if not attrs.get('generate') and not attrs.get('password'):
            raise serializers.ValidationError({'password': ['Set a password or choose to generate one.']})
        if not attrs.get('generate'):
            try:
                validate_password(attrs['password'], User(username=attrs['email'], email=attrs['email']))
            except DjangoValidationError as exc:
                raise serializers.ValidationError({'password': list(exc.messages)})
        return attrs


class UserUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120, required=False)
    role = serializers.ChoiceField(choices=Realm.choices, required=False)
    active = serializers.BooleanField(required=False)
    is_active = serializers.BooleanField(required=False)


class UserViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Dashboard accounts: admins and publishers. No hard delete: deactivate."""

    authentication_classes = [DashboardSessionAuthentication]
    permission_classes = [IsAdmin]
    serializer_class = UserSerializer
    pagination_class = DashboardPagination

    def get_queryset(self):
        admins = User.objects.filter(ADMIN_Q).values('pk')
        role = self.request.query_params.get('role')
        if role == Realm.ADMIN:
            ids = admins
        elif role == Realm.PUBLISHER:
            ids = User.objects.filter(PUBLISHER_Q).exclude(pk__in=admins).values('pk')
        else:
            ids = User.objects.filter(ADMIN_Q | PUBLISHER_Q).values('pk')
        return User.objects.filter(pk__in=ids).select_related('profile').order_by('email')

    def create(self, request):
        serializer = UserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data
        password = generate_password() if v.get('generate') else v['password']
        with transaction.atomic():
            user = User.objects.create_user(username=v['email'], email=v['email'], password=password)
            Profile.objects.create(user=user, name=v['name'], must_change_password=True)
            set_role(user, v['role'])
        sent = email_credentials(user, password)
        logger.info('Account %s created (%s) by user %s', user.pk, v['role'], request.user.pk)
        data = UserSerializer(user).data
        data['email_sent'] = sent
        return Response(data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        user = self.get_object()
        serializer = UserUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data
        active = v.get('active', v.get('is_active'))
        new_role = v.get('role')
        is_self = user.pk == request.user.pk
        currently_admin = role_of(user) == Realm.ADMIN and user.is_active
        loses_admin = currently_admin and (active is False or (new_role and new_role != Realm.ADMIN))
        if loses_admin:
            if is_self:
                raise ValidationError({'detail': 'You cannot deactivate or demote your own account.'})
            if not active_admins().exclude(pk=user.pk).exists():
                raise ValidationError({'detail': 'There must always be at least one active admin.'})
        elif active is False and is_self:
            raise ValidationError({'detail': 'You cannot deactivate your own account.'})
        with transaction.atomic():
            if 'name' in v:
                profile = profile_of(user)
                profile.name = v['name'].strip()
                profile.save(update_fields=['name'])
            if new_role and new_role != role_of(user):
                set_role(user, new_role)
            if active is not None and active != user.is_active:
                user.is_active = active
                # A deactivated user's session stops working on the next
                # request (ModelBackend refuses inactive users).
                user.save(update_fields=['is_active'])
        user.refresh_from_db()
        return Response(UserSerializer(user).data)

    def update(self, request, pk=None):
        return self.partial_update(request, pk)

    @action(detail=True, methods=['post'], url_path='reset-password')
    def reset_password(self, request, pk=None):
        user = self.get_object()
        password = generate_password()
        user.set_password(password)
        user.save(update_fields=['password'])
        profile = profile_of(user)
        profile.must_change_password = True
        profile.save(update_fields=['must_change_password'])
        if user.pk == request.user.pk:
            update_session_auth_hash(request._request, user)
        sent = email_credentials(user, password, reset=True)
        logger.info('Password reset for account %s by user %s', user.pk, request.user.pk)
        return Response({'ok': True, 'email_sent': sent})


class LoginEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoginEvent
        fields = ['id', 'created', 'realm', 'username', 'user', 'success', 'outcome', 'user_agent_family']


class LoginEventViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """GET manage/login-events/?realm=admin|publisher&success=true|false"""

    authentication_classes = [DashboardSessionAuthentication]
    permission_classes = [IsAdmin]
    serializer_class = LoginEventSerializer
    pagination_class = DashboardPagination

    def get_queryset(self):
        qs = LoginEvent.objects.all()
        realm = self.request.query_params.get('realm')
        if realm in Realm.values:
            qs = qs.filter(realm=realm)
        success = (self.request.query_params.get('success') or '').lower()
        if success in ('true', '1', 'false', '0'):
            qs = qs.filter(success=success in ('true', '1'))
        return qs
