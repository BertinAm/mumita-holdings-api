import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings

from accounts.auth import role_of

from .helpers import FRONTEND, DashboardTestCase, make_user

URL = '/api/v1/manage/users/'
User = get_user_model()


@override_settings(FRONTEND_URL=FRONTEND)
class UserTests(DashboardTestCase):
    def setUp(self):
        super().setUp()
        self.api = self.client_for(self.admin)

    def create(self, **data):
        body = {'name': 'New Person', 'email': 'test-new@mumitaholdings.com', 'role': 'publisher', 'generate': True}
        body.update(data)
        return self.api.post(URL, body, format='json')

    def test_list_requires_admin(self):
        self.assertEqual(self.client_for(None).get(URL).status_code, 401)
        self.assertEqual(self.client_for(self.pub).get(URL).status_code, 403)
        res = self.api.get(URL)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['count'], 3)
        publishers = self.api.get(URL + '?role=publisher').json()['results']
        self.assertEqual({u['email'] for u in publishers}, {self.pub.email, self.pub2.email})

    def test_create_with_generated_password_emails_credentials(self):
        res = self.create()
        self.assertEqual(res.status_code, 201, res.content)
        body = res.json()
        self.assertEqual((body['role'], body['must_change_password'], body['email_sent']), ('publisher', True, True))
        self.assertNotIn('password', body)
        user = User.objects.get(email='test-new@mumitaholdings.com')
        self.assertEqual(role_of(user), 'publisher')
        self.assertFalse(user.is_staff)
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, ['test-new@mumitaholdings.com'])
        password = re.search(r'Temporary password: (\S+)', msg.body).group(1)
        self.assertGreaterEqual(len(password), 20)
        self.assertTrue(user.check_password(password))
        html = msg.alternatives[0].content
        self.assertIn(password, html)
        self.assertIn(f'{FRONTEND}/write/login', msg.body)

    def test_admin_login_link_points_at_dashboard(self):
        self.create(role='admin', email='test-boss@mumitaholdings.com')
        self.assertIn(f'{FRONTEND}/dashboard/login', mail.outbox[0].body)
        self.assertTrue(User.objects.get(email='test-boss@mumitaholdings.com').is_superuser)

    def test_email_must_be_company_domain(self):
        for email in ('someone@example.com', 'x@mumitaholdings.com.evil.example', 'test-x@sub.mumitaholdings.com'):
            res = self.create(email=email)
            self.assertEqual(res.status_code, 400, email)
            self.assertIn('email', res.json())
        self.assertEqual(self.create(email='Test-Case@MUMITAHOLDINGS.com').status_code, 201)
        self.assertTrue(User.objects.filter(username='test-case@mumitaholdings.com').exists())

    def test_duplicate_email_refused(self):
        self.assertEqual(self.create(email=self.pub.email).status_code, 400)

    def test_set_password_is_validated(self):
        self.assertEqual(self.create(generate=False, password='short').status_code, 400)
        self.assertEqual(self.create(generate=False).status_code, 400)
        res = self.create(generate=False, password='test-A-Perfectly-Fine-Passphrase-7')
        self.assertEqual(res.status_code, 201)
        self.assertIn('test-A-Perfectly-Fine-Passphrase-7', mail.outbox[0].body)

    def test_patch_name_and_role(self):
        res = self.api.patch(f'{URL}{self.pub.pk}/', {'name': 'Renamed', 'role': 'admin'}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual((res.json()['name'], res.json()['role']), ('Renamed', 'admin'))

    def test_cannot_deactivate_self(self):
        res = self.api.patch(f'{URL}{self.admin.pk}/', {'active': False}, format='json')
        self.assertEqual(res.status_code, 400)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_admin_can_remove_another_admin_but_not_demote_self(self):
        other = make_user('test-admin2@mumitaholdings.com', 'admin')
        api = self.client_for(other)
        self.assertEqual(api.patch(f'{URL}{self.admin.pk}/', {'role': 'publisher'}, format='json').status_code, 200)
        self.assertEqual(role_of(User.objects.get(pk=self.admin.pk)), 'publisher')
        # `other` is now the last active admin and cannot demote itself.
        res = api.patch(f'{URL}{other.pk}/', {'role': 'publisher'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(role_of(User.objects.get(pk=other.pk)), 'admin')

    def test_last_admin_rule_counts_only_active_admins(self):
        other = make_user('test-admin2@mumitaholdings.com', 'admin', active=False)
        # `other` is inactive, so self.admin is the only active admin.
        res = self.client_for(self.admin).patch(f'{URL}{self.admin.pk}/', {'active': False}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertFalse(User.objects.get(pk=other.pk).is_active)

    def test_deactivated_user_session_stops_working(self):
        pub_api = self.client_for(self.pub)
        self.assertEqual(pub_api.get('/api/v1/write/posts/').status_code, 200)
        self.api.patch(f'{URL}{self.pub.pk}/', {'active': False}, format='json')
        self.assertEqual(pub_api.get('/api/v1/write/posts/').status_code, 401)

    def test_reset_password(self):
        old_hash = self.pub.password
        res = self.api.post(f'{URL}{self.pub.pk}/reset-password/')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['email_sent'])
        self.pub.refresh_from_db()
        self.assertNotEqual(self.pub.password, old_hash)
        self.assertTrue(self.pub.profile.must_change_password)
        password = re.search(r'Temporary password: (\S+)', mail.outbox[0].body).group(1)
        self.assertTrue(self.pub.check_password(password))
        self.assertIn('reset', mail.outbox[0].subject)
