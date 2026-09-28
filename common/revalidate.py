"""On-demand revalidation of the Next.js site (PLATFORM-CONTRACT "Post
workflow").

    POST {DJANGO_FRONTEND_URL}/api/revalidate
    X-Revalidate-Key: <REVALIDATE_KEY>
    {"paths": ["/blog", "/blog/<slug>", "/gallery", "/"]}

Called after the database transaction commits. A failure is logged and never
raised.

On the Free plan without R2 the Worker's page cache is read-only, so each
change also records a rebuild request (content.FrontendRebuild); the cron
job `manage.py rebuild_frontend` then calls the Workers Builds deploy hook
(DEPLOY.md 2.8).
"""

import json
import logging
import urllib.request

from django.conf import settings
from django.db import transaction

logger = logging.getLogger('common.revalidate')

BLOG = '/blog'
GALLERY = '/gallery'
HOME = '/'


def post_paths(*slugs):
    return [BLOG, *(f'{BLOG}/{slug}' for slug in slugs if slug), HOME]


def _post(paths):
    request = urllib.request.Request(
        f'{settings.FRONTEND_URL}/api/revalidate',
        data=json.dumps({'paths': paths}).encode(),
        headers={'Content-Type': 'application/json', 'X-Revalidate-Key': settings.REVALIDATE_KEY},
        method='POST',
    )
    with urllib.request.urlopen(request, timeout=settings.REVALIDATE_TIMEOUT) as response:
        return response.status


def send(paths):
    paths = list(dict.fromkeys(paths))
    if not (settings.FRONTEND_URL and settings.REVALIDATE_KEY):
        logger.info('Revalidation skipped (DJANGO_FRONTEND_URL or REVALIDATE_KEY unset): %s', paths)
        return False
    try:
        code = _post(paths)
    except Exception as exc:
        logger.warning('Revalidation failed for %s: %s', paths, exc.__class__.__name__)
        return False
    logger.info('Revalidated %s (%s)', paths, code)
    return True


def request_rebuild():
    from content.models import FrontendRebuild

    try:
        FrontendRebuild.request()
    except Exception as exc:  # never break a save over this
        logger.warning('Rebuild request not recorded: %s', exc.__class__.__name__)


def revalidate(paths):
    """Queue a revalidation (and a rebuild request) for after the current
    transaction commits."""
    paths = list(paths)

    def after_commit():
        request_rebuild()
        send(paths)

    transaction.on_commit(after_commit)
