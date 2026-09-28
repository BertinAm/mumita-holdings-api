import re
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import CommandError, call_command
from django.test import TestCase

from accounts.auth import role_of
from content.models import Post


class CommandTests(TestCase):
    def test_create_admin_prints_password_once(self):
        out = StringIO()
        call_command('create_admin', email='Test-First@mumitaholdings.com', name='First Admin', stdout=out)
        text = out.getvalue()
        password = re.search(r'^\s{4}(\S+)$', text, re.M).group(1)
        self.assertEqual(text.count(password), 1)
        user = get_user_model().objects.get(username='test-first@mumitaholdings.com')
        self.assertTrue(user.check_password(password))
        self.assertEqual(role_of(user), 'admin')
        self.assertTrue(user.profile.must_change_password)
        self.assertEqual(len(mail.outbox), 0)
        with self.assertRaises(CommandError):
            call_command('create_admin', email='test-first@mumitaholdings.com', name='Again', stdout=StringIO())

    def test_create_admin_requires_company_domain(self):
        with self.assertRaises(CommandError):
            call_command('create_admin', email='someone@example.com', name='X', stdout=StringIO())

    def test_send_test_email(self):
        call_command('send_test_email', 'someone@example.com', stdout=StringIO())
        self.assertEqual(mail.outbox[0].to, ['someone@example.com'])
        self.assertTrue(mail.outbox[0].alternatives)

    def test_seed_posts_keeps_original_dates(self):
        call_command('seed_posts', stdout=StringIO())
        call_command('seed_posts', stdout=StringIO())  # idempotent
        self.assertEqual(Post.objects.count(), 6)
        dates = [p.published_at.date().isoformat() for p in Post.objects.order_by('-published_at')]
        self.assertEqual(dates, ['2020-01-09', '2019-09-08', '2019-05-24', '2019-03-08', '2018-11-28', '2018-11-02'])
        post = Post.objects.get(slug='why-food-quality-matters-a-guide-for-farmers-and-consumers')
        self.assertEqual(post.author_name, 'Mumita Holdings')
        self.assertTrue(post.body.startswith('<p>'))
        self.assertIn('<strong>', post.body)
        self.assertNotIn('<b>', post.body)
        res = self.client.get('/api/v1/posts/').json()
        self.assertEqual(res['count'], 6)
        self.assertEqual(res['results'][0]['media_key'], '2025-06-img-8009')

    def test_env_example_documents_every_setting(self):
        source = (Path(settings.BASE_DIR) / 'config' / 'settings.py').read_text()
        names = set(re.findall(r"""(?:env_\w+|os\.environ\.get|os\.environ\[)\(?'([A-Z_]+)'""", source))
        example = (Path(settings.BASE_DIR) / '.env.example').read_text()
        documented = set(re.findall(r'^#?\s?([A-Z_]+)=', example, re.M))
        self.assertEqual(names - documented, set())
