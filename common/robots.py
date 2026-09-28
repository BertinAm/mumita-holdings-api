"""Keep search engines out of the API and the Django admin.

api.mumitaholdings.com serves JSON, the dashboards' endpoints and the
Django admin: none of it belongs in a search index. Every response gets
`X-Robots-Tag: noindex, nofollow, noarchive`, and /robots.txt disallows
everything. The exception is /media/ (gallery and article images shown on
the public site), which stays indexable so the photos can appear in image
search next to the pages that use them.
"""

from django.conf import settings
from django.http import HttpResponse

NOINDEX = 'noindex, nofollow, noarchive'


def _is_media(path: str) -> bool:
    media = '/' + settings.MEDIA_URL.strip('/') + '/'
    return path.startswith(media)


class NoIndexMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not _is_media(request.path):
            response.setdefault('X-Robots-Tag', NOINDEX)
        return response


def robots_txt(request):
    media = '/' + settings.MEDIA_URL.strip('/') + '/'
    body = f'User-agent: *\nAllow: {media}\nDisallow: /\n'
    return HttpResponse(body, content_type='text/plain; charset=utf-8')
