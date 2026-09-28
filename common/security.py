"""Small privacy helpers shared by enquiries, testimonials, sign-in logs,
DRF throttling and django-axes.

Client IP (never stored; only a keyed hash is):

1. A request from a *trusted forwarder* (the frontend Worker) carries the
   visitor's IP in DJANGO_TRUSTED_PROXY_HEADER (default X-Forwarded-For),
   and its first hop is used. A request is from a trusted forwarder only when
   it carries `X-Proxy-Key: <DJANGO_TRUSTED_PROXY_KEY>`, or its REMOTE_ADDR
   is inside DJANGO_TRUSTED_PROXIES (IPs/CIDRs). Both are unset by default,
   so nothing is trusted.
2. Otherwise, with DJANGO_NUM_PROXIES = n > 0 (proxies of our own hosting
   that append to X-Forwarded-For), the n-th address from the right, as in
   DRF's NUM_PROXIES.
3. Otherwise REMOTE_ADDR.
"""

import hashlib
import hmac
import ipaddress
import re
from functools import lru_cache

from django.conf import settings
from rest_framework.throttling import ScopedRateThrottle


def _ip(value):
    try:
        return str(ipaddress.ip_address((value or '').strip()))
    except ValueError:
        return None


@lru_cache(maxsize=8)
def _networks(spec):
    nets = []
    for item in spec:
        try:
            nets.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            continue
    return tuple(nets)


def from_trusted_forwarder(request):
    key = settings.TRUSTED_PROXY_KEY
    if key:
        given = request.headers.get('X-Proxy-Key', '')
        if given and hmac.compare_digest(given.encode(), key.encode()):
            return True
    nets = _networks(tuple(settings.TRUSTED_PROXIES))
    remote = _ip(request.META.get('REMOTE_ADDR'))
    if nets and remote:
        addr = ipaddress.ip_address(remote)
        return any(addr in net for net in nets)
    return False


def client_ip(request):
    """The visitor's IP address (see the module docstring). Accepts a Django
    HttpRequest or a DRF Request."""
    if from_trusted_forwarder(request):
        forwarded = request.headers.get(settings.TRUSTED_PROXY_HEADER, '')
        ip = _ip(forwarded.split(',')[0])
        if ip:
            return ip
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    n = settings.NUM_PROXIES
    if n and xff:
        addrs = xff.split(',')
        ip = _ip(addrs[-min(n, len(addrs))])
        if ip:
            return ip
    return request.META.get('REMOTE_ADDR', '')


class ClientIPScopedRateThrottle(ScopedRateThrottle):
    """DRF scoped throttle keyed on client_ip()."""

    def get_ident(self, request):
        return client_ip(request)


def hash_ip(ip):
    """A keyed hash of an IP address. The IP itself is never stored."""
    if not ip:
        return ''
    return hmac.new(settings.SECRET_KEY.encode(), ip.encode(), hashlib.sha256).hexdigest()


_BROWSERS = (
    # Order matters: Edge and Opera also say Chrome; Chrome also says Safari.
    ('Edge', re.compile(r'Edg(e|A|iOS)?/')),
    ('Opera', re.compile(r'OPR/|Opera')),
    ('Samsung Internet', re.compile(r'SamsungBrowser/')),
    ('Firefox', re.compile(r'Firefox/|FxiOS/')),
    ('Chrome', re.compile(r'Chrome/|CriOS/')),
    ('Safari', re.compile(r'Safari/')),
)
_SYSTEMS = (
    ('Android', re.compile(r'Android')),
    ('iOS', re.compile(r'iPhone|iPad|iPod')),
    ('Windows', re.compile(r'Windows')),
    ('macOS', re.compile(r'Mac OS X|Macintosh')),
    ('Linux', re.compile(r'Linux|X11')),
)
_TOOLS = re.compile(r'curl|wget|python|httpie|postman|go-http|java/|okhttp|node-fetch|undici', re.I)
_BOTS = re.compile(r'bot|crawl|spider|slurp|headless', re.I)


def user_agent_family(ua):
    """'Chrome on macOS', 'Firefox on Windows', 'Script', 'Bot' or 'Other'.
    Only the family is kept, never the full string."""
    ua = ua or ''
    if not ua:
        return ''
    if _BOTS.search(ua):
        return 'Bot'
    if _TOOLS.search(ua):
        return 'Script'
    browser = next((name for name, rx in _BROWSERS if rx.search(ua)), 'Other')
    system = next((name for name, rx in _SYSTEMS if rx.search(ua)), '')
    return f'{browser} on {system}' if system else browser
