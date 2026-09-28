import json
from unittest import mock

from django.test import SimpleTestCase, override_settings

from common import revalidate


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@override_settings(FRONTEND_URL='https://frontend.example', REVALIDATE_KEY='test-key', REVALIDATE_TIMEOUT=3)
class RevalidateTests(SimpleTestCase):
    @mock.patch('urllib.request.urlopen', return_value=FakeResponse())
    def test_posts_paths_with_key(self, urlopen):
        self.assertTrue(revalidate.send(revalidate.post_paths('old', 'new')))
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, 'https://frontend.example/api/revalidate')
        self.assertEqual(request.get_header('X-revalidate-key'), 'test-key')
        self.assertEqual(json.loads(request.data), {'paths': ['/blog', '/blog/old', '/blog/new', '/']})
        self.assertEqual(urlopen.call_args.kwargs['timeout'], 3)

    @mock.patch('urllib.request.urlopen', side_effect=TimeoutError())
    def test_failure_is_logged_not_raised(self, urlopen):
        with self.assertLogs('common.revalidate', level='WARNING'):
            self.assertFalse(revalidate.send(['/']))

    @override_settings(REVALIDATE_KEY='')
    @mock.patch('urllib.request.urlopen')
    def test_skipped_without_key(self, urlopen):
        self.assertFalse(revalidate.send(['/']))
        urlopen.assert_not_called()
