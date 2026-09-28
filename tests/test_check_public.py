import importlib.util
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

spec = importlib.util.spec_from_file_location('check_public', Path(settings.BASE_DIR) / 'scripts' / 'check_public.py')
check_public = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_public)


class CheckPublicTests(SimpleTestCase):
    def test_emails(self):
        ok = check_public.email_ok
        self.assertTrue(ok('info@mumitaholdings.com'))
        self.assertTrue(ok('test-admin@mumitaholdings.com'))
        self.assertTrue(ok('ada@example.com'))
        self.assertFalse(ok('jane.doe@gmail.com'))  # check_public: ignore
        self.assertFalse(ok('jane@mumitaholdings.com'))  # check_public: ignore

    def test_secret_assignments(self):
        line = 'DJANGO_SECRET_KEY=abc123realsecretvalue'  # check_public: ignore
        self.assertTrue(any(not check_public.PLACEHOLDER.match(m.group('value'))
                            for m in check_public.ASSIGNMENT.finditer(line)))
        line = 'DJANGO_SECRET_KEY=change-me-long-random-string'
        self.assertFalse(any(not check_public.PLACEHOLDER.match(m.group('value'))
                             for m in check_public.ASSIGNMENT.finditer(line)))

    def test_forbidden_names(self):
        for name in ('.env', 'db.sqlite3', 'backup.sql', 'x.pem', 'config/.env.production'):
            self.assertTrue(check_public.FORBIDDEN_NAME.search(name), name)
        self.assertIsNone(check_public.FORBIDDEN_NAME.search('README.md'))

    def test_repository_is_clean(self):
        if not (Path(settings.BASE_DIR) / '.git').exists() and not (Path(settings.BASE_DIR).parent.parent / '.git').exists():
            self.skipTest('not a git checkout')
        self.assertEqual(check_public.main(['--tracked']), 0)
