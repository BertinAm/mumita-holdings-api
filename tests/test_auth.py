from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import LoginEvent

from .helpers import PASSWORD, make_user

LOGIN = '/api/v1/auth/login/'
ME = '/api/v1/auth/me/'
CHROME_MAC = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36'


class AuthTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.admin = make_user('test-admin@mumitaholdings.com', 'admin', name='Admin One')
        self.pub = make_user('test-pub@mumitaholdings.com', 'publisher', name='Pub One')

    def login(self, email, realm, password=PASSWORD, client=None):
        return (client or self.client).post(
            LOGIN, {'email': email, 'password': password, 'realm': realm}, format='json', HTTP_USER_AGENT=CHROME_MAC,
        )

    def test_csrf_endpoint_sets_cookie(self):
        res = self.client.get('/api/v1/auth/csrf/')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['ok'])
        self.assertIn('csrftoken', res.cookies)
        self.assertGreaterEqual(len(res.json()['csrfToken']), 32)

    def test_admin_signs_in_to_admin_realm(self):
        res = self.login('test-admin@mumitaholdings.com', 'admin')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['user'], {
            'id': self.admin.pk, 'name': 'Admin One', 'email': 'test-admin@mumitaholdings.com',
            'role': 'admin', 'must_change_password': False,
        })
        self.assertIn('sessionid', res.cookies)
        self.assertTrue(res.cookies['sessionid']['httponly'])
        self.assertEqual(self.client.get(ME).json()['role'], 'admin')
        event = LoginEvent.objects.get()
        self.assertEqual((event.success, event.outcome, event.realm, event.user), (True, 'success', 'admin', self.admin))
        self.assertEqual(event.user_agent_family, 'Chrome on macOS')
        self.assertEqual(len(event.ip_hash), 64)

    def test_email_is_case_insensitive(self):
        self.assertEqual(self.login('Test-Admin@MumitaHoldings.com', 'admin').status_code, 200)

    def test_publisher_refused_at_admin_realm_with_generic_error(self):
        bad = self.login('test-admin@mumitaholdings.com', 'admin', password='test-wrong-password')
        wrong_realm = self.login('test-pub@mumitaholdings.com', 'admin')
        self.assertEqual(wrong_realm.status_code, 400)
        self.assertEqual(wrong_realm.json(), bad.json())
        self.assertNotIn('sessionid', wrong_realm.cookies)
        self.assertEqual(self.client.get(ME).status_code, 401)
        self.assertEqual(LoginEvent.objects.filter(outcome='wrong_realm').count(), 1)

    def test_admin_refused_at_publisher_realm(self):
        res = self.login('test-admin@mumitaholdings.com', 'publisher')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json(), {'detail': 'Invalid email or password.'})

    def test_publisher_signs_in_to_publisher_realm(self):
        res = self.login('test-pub@mumitaholdings.com', 'publisher')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['user']['role'], 'publisher')

    def test_unknown_email_and_bad_password_are_recorded(self):
        self.assertEqual(self.login('test-nobody@mumitaholdings.com', 'admin').status_code, 400)
        self.assertEqual(self.login('test-admin@mumitaholdings.com', 'admin', password='test-nope-nope').status_code, 400)
        events = list(LoginEvent.objects.order_by('pk').values_list('username', 'success', 'outcome'))
        self.assertEqual(events, [
            ('test-nobody@mumitaholdings.com', False, 'bad_credentials'),
            ('test-admin@mumitaholdings.com', False, 'bad_credentials'),
        ])

    def test_inactive_account_refused(self):
        self.admin.is_active = False
        self.admin.save()
        res = self.login('test-admin@mumitaholdings.com', 'admin')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json(), {'detail': 'Invalid email or password.'})
        self.assertEqual(LoginEvent.objects.get().outcome, 'inactive')

    def test_malformed_body_is_generic_400(self):
        res = self.client.post(LOGIN, {'email': 'x', 'realm': 'root'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json(), {'detail': 'Invalid email or password.'})

    def test_axes_locks_out_after_limit(self):
        for _ in range(settings.AXES_FAILURE_LIMIT - 1):
            self.assertEqual(self.login('test-admin@mumitaholdings.com', 'admin', password='test-bad-bad').status_code, 400)
        locked = self.login('test-admin@mumitaholdings.com', 'admin', password='test-bad-bad')
        self.assertEqual(locked.status_code, 429)
        self.assertEqual(locked.json(), {'detail': 'locked'})
        # Even the right password is refused while locked.
        self.assertEqual(self.login('test-admin@mumitaholdings.com', 'admin').status_code, 429)
        self.assertTrue(LoginEvent.objects.filter(outcome='locked').exists())

    def test_me_requires_session(self):
        res = self.client.get(ME)
        self.assertEqual(res.status_code, 401)

    def test_logout_clears_session(self):
        self.login('test-admin@mumitaholdings.com', 'admin')
        self.assertEqual(self.client.post('/api/v1/auth/logout/').status_code, 200)
        self.assertEqual(self.client.get(ME).status_code, 401)

    def test_login_enforces_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        res = self.login('test-admin@mumitaholdings.com', 'admin', client=client)
        self.assertEqual(res.status_code, 403)
        token = client.get('/api/v1/auth/csrf/').json()['csrfToken']
        res = client.post(
            LOGIN, {'email': 'test-admin@mumitaholdings.com', 'password': PASSWORD, 'realm': 'admin'},
            format='json', HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res.status_code, 200, res.content)

    def test_session_settings(self):
        self.assertEqual(settings.SESSION_COOKIE_AGE, 8 * 3600)
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)
        self.assertTrue(settings.CORS_ALLOW_CREDENTIALS)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, 'Lax')

    @override_settings(SESSION_COOKIE_DOMAIN='.mumitaholdings.com')
    def test_cookie_domain_is_applied(self):
        res = self.login('test-admin@mumitaholdings.com', 'admin')
        self.assertEqual(res.cookies['sessionid']['domain'], '.mumitaholdings.com')


class PasswordTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user('test-new@mumitaholdings.com', 'publisher', must_change=True)
        self.client = APIClient()
        self.client.post(LOGIN, {'email': self.user.email, 'password': PASSWORD, 'realm': 'publisher'}, format='json')

    def change(self, current, new):
        return self.client.post('/api/v1/auth/password/', {'current': current, 'new': new}, format='json')

    def test_must_change_password_blocks_the_api_but_not_me(self):
        me = self.client.get(ME).json()
        self.assertTrue(me['must_change_password'])
        res = self.client.get('/api/v1/write/posts/')
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json(), {'detail': 'password_change_required'})

    def test_wrong_current_password(self):
        self.assertEqual(self.change('not-it-at-all', 'An0ther-Long-Passphrase').status_code, 400)

    def test_validators_apply(self):
        res = self.change(PASSWORD, 'short')
        self.assertEqual(res.status_code, 400)
        self.assertIn('new', res.json())
        self.assertEqual(self.change(PASSWORD, '123456789012345').status_code, 400)  # numeric only

    def test_change_clears_flag_and_keeps_session(self):
        res = self.change(PASSWORD, 'An0ther-Long-Passphrase')
        self.assertEqual(res.status_code, 200, res.content)
        me = self.client.get(ME).json()
        self.assertFalse(me['must_change_password'])
        self.assertEqual(self.client.get('/api/v1/write/posts/').status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('An0ther-Long-Passphrase'))

    def test_requires_sign_in(self):
        res = APIClient().post('/api/v1/auth/password/', {'current': 'a', 'new': 'b'}, format='json')
        self.assertEqual(res.status_code, 401)
