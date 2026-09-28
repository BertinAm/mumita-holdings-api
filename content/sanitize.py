"""Article HTML sanitization (PLATFORM-CONTRACT "Article body").

The editor stores HTML. Everything is cleaned by nh3 (ammonia) to the
contract's allow-list. On top of that:

- links keep http(s), mailto and tel only; external links get
  rel="noopener noreferrer"; target is either _blank or dropped;
- images must point at our own uploaded media (MEDIA_URL + "uploads/", on a
  relative path, this API's host or DJANGO_MEDIA_BASE_URL). Any other <img>
  is removed.
"""

import re
from urllib.parse import urlsplit

import nh3
from django.conf import settings

TAGS = {
    'p', 'h2', 'h3', 'h4', 'strong', 'em', 'u', 's', 'a', 'ul', 'ol', 'li', 'blockquote', 'code', 'pre',
    'hr', 'img', 'figure', 'figcaption', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'br',
}
ATTRIBUTES = {
    'a': {'href', 'rel', 'target'},
    'img': {'src', 'alt', 'width', 'height'},
}
URL_SCHEMES = {'http', 'https', 'mailto', 'tel'}
REL_TOKENS = {'noopener', 'noreferrer', 'nofollow', 'ugc', 'sponsored'}
EXTERNAL_REL = 'noopener noreferrer'

_A_TAG = re.compile(r'<a\b([^>]*)>')
_IMG_TAG = re.compile(r'<img\b[^>]*>')
_ATTR = re.compile(r'\s([a-z-]+)="([^"]*)"')


def _media_prefix():
    return settings.MEDIA_URL.rstrip('/') + '/uploads/'


def _media_hosts():
    hosts = {h.lstrip('.') for h in settings.ALLOWED_HOSTS if h not in ('*',)}
    if settings.MEDIA_BASE_URL:
        hosts.add(urlsplit(settings.MEDIA_BASE_URL).hostname or '')
    return {h.lower() for h in hosts if h}


def is_our_media(src):
    if not src:
        return False
    parts = urlsplit(src)
    if '..' in parts.path or not parts.path.startswith(_media_prefix()):
        return False
    if not parts.scheme and not parts.netloc:
        return True
    return parts.scheme in ('http', 'https') and (parts.hostname or '').lower() in _media_hosts()


def is_external(href):
    parts = urlsplit(href)
    if parts.scheme not in ('http', 'https'):
        return False
    host = (parts.hostname or '').lower()
    for ours in settings.SITE_HOSTS:
        ours = ours.lower().lstrip('.')
        if ours and (host == ours or host.endswith('.' + ours)):
            return False
    return True


def _attribute_filter(tag, attr, value):
    if tag == 'img':
        if attr == 'src':
            return value if is_our_media(value) else None
        if attr in ('width', 'height'):
            return value if value.isdigit() and 0 < int(value) <= 4000 else None
    if tag == 'a':
        if attr == 'target':
            return '_blank' if value == '_blank' else None
        if attr == 'rel':
            tokens = [t for t in value.lower().split() if t in REL_TOKENS]
            return ' '.join(dict.fromkeys(tokens)) or None
    return value


def _fix_link(match):
    attrs = dict(_ATTR.findall(match.group(0)))
    href = attrs.get('href', '')
    rel = attrs.get('rel', '').split()
    if href and is_external(href) or attrs.get('target') == '_blank':
        rel = list(dict.fromkeys(rel + EXTERNAL_REL.split()))
    if rel:
        attrs['rel'] = ' '.join(rel)
    else:
        attrs.pop('rel', None)
    order = [k for k in ('href', 'rel', 'target') if k in attrs]
    inner = ''.join(f' {k}="{attrs[k]}"' for k in order)
    return f'<a{inner}>'


def sanitize_html(html):
    if not html:
        return ''
    cleaned = nh3.clean(
        html,
        tags=TAGS,
        attributes=ATTRIBUTES,
        url_schemes=URL_SCHEMES,
        link_rel=None,
        strip_comments=True,
        attribute_filter=_attribute_filter,
        clean_content_tags={'script', 'style'},
    )
    cleaned = _IMG_TAG.sub(lambda m: m.group(0) if ' src="' in m.group(0) else '', cleaned)
    cleaned = _A_TAG.sub(_fix_link, cleaned)
    return cleaned.strip()
