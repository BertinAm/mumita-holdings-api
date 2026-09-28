from django.test import TestCase


class NoIndexTests(TestCase):
    def test_api_responses_are_noindex(self):
        r = self.client.get('/api/v1/posts/')
        self.assertEqual(r['X-Robots-Tag'], 'noindex, nofollow, noarchive')

    def test_auth_and_manage_responses_are_noindex(self):
        for path in ('/api/v1/auth/me/', '/api/v1/manage/stats/', '/api/v1/write/posts/'):
            r = self.client.get(path)
            self.assertEqual(r['X-Robots-Tag'], 'noindex, nofollow, noarchive', path)

    def test_robots_txt_disallows_all_but_media(self):
        r = self.client.get('/robots.txt')
        self.assertEqual(r.status_code, 200)
        body = r.content.decode()
        self.assertIn('Disallow: /\n', body)
        self.assertIn('Allow: /media/', body)
        self.assertEqual(r['X-Robots-Tag'], 'noindex, nofollow, noarchive')
