"""Transactional email: a plain-text body plus an HTML alternative, both
rendered from templates/email/<name>.txt|.html. Failures are logged (never
with the message content) and reported to the caller, not raised."""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger('common.mail')


def send_email(to, subject, template, context=None, reply_to=None):
    to = [address for address in to if address]
    if not to:
        logger.warning('Email %s not sent: no recipients', template)
        return False
    context = {'frontend_url': settings.FRONTEND_URL, 'subject': subject, **(context or {})}
    text = render_to_string(f'email/{template}.txt', context)
    html = render_to_string(f'email/{template}.html', context)
    message = EmailMultiAlternatives(
        subject=subject, body=text, from_email=settings.DEFAULT_FROM_EMAIL, to=to, reply_to=reply_to or None,
    )
    message.attach_alternative(html, 'text/html')
    try:
        message.send()
    except Exception:
        logger.exception('Email %s to %d recipient(s) failed', template, len(to))
        return False
    logger.info('Email %s sent to %d recipient(s)', template, len(to))
    return True
