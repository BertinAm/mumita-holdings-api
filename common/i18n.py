"""Locale resolution for the API.

The six site locales use the frontend's codes (src/i18n/locales.ts):
en, fr, sw, es, zh, pt. A request picks its locale with `?lang=` first, then
the Accept-Language header, then falls back to English. Translated model
fields fall back to English when the requested locale is empty
(MODELTRANSLATION_FALLBACK_LANGUAGES), so a half-translated row never
returns blanks.
"""

from django.conf import settings
from django.utils import translation
from django.utils.translation.trans_real import parse_accept_lang_header

SITE_LOCALES = tuple(code for code, _ in settings.LANGUAGES)
DEFAULT_LOCALE = settings.MODELTRANSLATION_DEFAULT_LANGUAGE
ENGLISH_ONLY_PREFIXES = ('/api/v1/auth/', '/api/v1/manage/', '/api/v1/write/')


def normalise(code):
    """Map 'fr-FR', 'zh-Hans', 'PT_br' etc. onto a site locale, or None."""
    if not code:
        return None
    primary = code.strip().lower().replace('_', '-').split('-')[0]
    return primary if primary in SITE_LOCALES else None


def locale_from_request(request):
    lang = normalise(request.GET.get('lang'))
    if lang:
        return lang
    header = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
    for code, _q in parse_accept_lang_header(header):
        lang = normalise(code)
        if lang:
            return lang
    return DEFAULT_LOCALE


class ApiLocaleMiddleware:
    """Activate the request locale for /api/ paths only.

    Django's own LocaleMiddleware is not used: it would ignore `?lang=` and
    reject codes Django ships no catalogue for (sw).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith('/api/'):
            return self.get_response(request)
        # The dashboards are English-only and write the English columns:
        # never let a browser's Accept-Language redirect their writes.
        if request.path.startswith(ENGLISH_ONLY_PREFIXES):
            lang = DEFAULT_LOCALE
        else:
            lang = locale_from_request(request)
        request.LANGUAGE_CODE = lang
        with translation.override(lang):
            response = self.get_response(request)
        response.headers.setdefault('Content-Language', lang)
        vary = response.headers.get('Vary', '')
        if 'accept-language' not in vary.lower():
            response.headers['Vary'] = f'{vary}, Accept-Language' if vary else 'Accept-Language'
        return response
