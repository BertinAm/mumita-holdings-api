"""`check --deploy` warnings for the settings the platform contract needs."""

from django.conf import settings
from django.core.checks import Tags, Warning, register


@register(Tags.security, deploy=True)
def platform_settings(app_configs, **kwargs):
    issues = []
    required = {
        'FRONTEND_URL': 'DJANGO_FRONTEND_URL',
        'REVALIDATE_KEY': 'REVALIDATE_KEY',
        'ANALYTICS_INGEST_KEY': 'ANALYTICS_INGEST_KEY',
        'CORS_ALLOWED_ORIGINS': 'DJANGO_CORS_ALLOWED_ORIGINS',
    }
    for attr, env in required.items():
        if not getattr(settings, attr, None):
            issues.append(Warning(f'{env} is not set.', id=f'mumita.W{len(issues) + 1:03d}'))
    if not settings.SESSION_COOKIE_DOMAIN:
        issues.append(Warning(
            'DJANGO_COOKIE_DOMAIN is not set: the dashboards on the main domain cannot share the session.',
            id='mumita.W010',
        ))
    if settings.NUM_PROXIES and not (settings.TRUSTED_PROXY_KEY or settings.TRUSTED_PROXIES):
        issues.append(Warning(
            'DJANGO_NUM_PROXIES > 0 trusts X-Forwarded-For from every request. Set it only when a proxy of '
            'our own hosting appends that header; use DJANGO_TRUSTED_PROXY_KEY for the frontend Worker.',
            id='mumita.W011',
        ))
    return issues
