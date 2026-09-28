"""Rebuild the frontend when public content has changed (cron, every 5 min).

    */5 * * * *  cd ~/api.mumitaholdings.com && ~/virtualenv/.../bin/python manage.py rebuild_frontend

Pages on the Worker are static per build (Free plan without R2, DEPLOY.md
2.8). Every publish, unpublish, gallery or testimonial change records a
request (content.FrontendRebuild); this command POSTs the Workers Builds
deploy hook once if a request is newer than the last trigger, so a burst of
edits costs one build. With --force it triggers regardless.
"""

import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from content.models import FrontendRebuild


def post_hook(url, timeout=15):
    request = urllib.request.Request(url, data=b'', method='POST')
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status


class Command(BaseCommand):
    help = 'Trigger a frontend rebuild through the deploy hook if content changed.'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Trigger even if nothing changed.')

    def handle(self, *args, force=False, **options):
        url = settings.FRONTEND_DEPLOY_HOOK_URL
        if not url:
            self.stdout.write('FRONTEND_DEPLOY_HOOK_URL is not set; nothing to do.')
            return
        state, _ = FrontendRebuild.objects.get_or_create(pk=1)
        pending = state.requested_at and (not state.triggered_at or state.requested_at > state.triggered_at)
        if not (pending or force):
            self.stdout.write('No content change since the last rebuild.')
            return
        started = timezone.now()
        try:
            code = post_hook(url)
        except Exception as exc:
            state.last_status = f'failed: {exc.__class__.__name__}'[:40]
            state.save(update_fields=['last_status'])
            self.stderr.write(f'Deploy hook failed: {exc.__class__.__name__}')
            return
        state.triggered_at = started
        state.last_status = f'HTTP {code}'
        state.save(update_fields=['triggered_at', 'last_status'])
        self.stdout.write(self.style.SUCCESS(f'Rebuild triggered (HTTP {code}).'))
