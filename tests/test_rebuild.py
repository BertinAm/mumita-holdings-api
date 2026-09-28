from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings

from common import revalidate
from content.models import FrontendRebuild

HOOK = 'https://api.cloudflare.com/client/v4/workers/builds/deploy_hooks/test-hook-id'


class RebuildTests(TestCase):
    def run_cmd(self, *args):
        out = StringIO()
        call_command('rebuild_frontend', *args, stdout=out, stderr=out)
        return out.getvalue()

    def test_content_change_records_a_request(self):
        with mock.patch.object(revalidate, 'send'), self.captureOnCommitCallbacks(execute=True):
            revalidate.revalidate(['/blog'])
        self.assertIsNotNone(FrontendRebuild.objects.get(pk=1).requested_at)

    @override_settings(FRONTEND_DEPLOY_HOOK_URL=HOOK)
    def test_triggers_once_per_change(self):
        FrontendRebuild.request()
        with mock.patch('content.management.commands.rebuild_frontend.post_hook', return_value=200) as hook:
            self.assertIn('Rebuild triggered', self.run_cmd())
            self.assertIn('No content change', self.run_cmd())
        hook.assert_called_once_with(HOOK)
        state = FrontendRebuild.objects.get(pk=1)
        self.assertEqual(state.last_status, 'HTTP 200')
        self.assertGreaterEqual(state.triggered_at, state.requested_at)

    @override_settings(FRONTEND_DEPLOY_HOOK_URL=HOOK)
    def test_failure_keeps_the_request_pending(self):
        FrontendRebuild.request()
        with mock.patch('content.management.commands.rebuild_frontend.post_hook', side_effect=OSError):
            self.assertIn('failed', self.run_cmd())
        self.assertIsNone(FrontendRebuild.objects.get(pk=1).triggered_at)

    @override_settings(FRONTEND_DEPLOY_HOOK_URL=HOOK)
    def test_force(self):
        with mock.patch('content.management.commands.rebuild_frontend.post_hook', return_value=200) as hook:
            self.assertIn('No content change', self.run_cmd())
            self.assertIn('Rebuild triggered', self.run_cmd('--force'))
        hook.assert_called_once()

    @override_settings(FRONTEND_DEPLOY_HOOK_URL='')
    def test_without_hook_does_nothing(self):
        FrontendRebuild.request()
        self.assertIn('not set', self.run_cmd())
