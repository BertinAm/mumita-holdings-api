import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def notify_staff(enquiry):
    """Email the enquiry to staff. The body carries the visitor's details
    because staff need them to reply; logs never do (see logger calls:
    id and type only)."""
    recipients = settings.ENQUIRY_NOTIFY_EMAILS
    if not recipients:
        logger.warning('Enquiry %s stored; ENQUIRY_NOTIFY_EMAILS is empty, no email sent', enquiry.pk)
        return False
    subject = f'[Mumita website] New enquiry: {enquiry.get_enquiry_type_display()}'
    body = (
        f'Type: {enquiry.get_enquiry_type_display()}\n'
        f'Name: {enquiry.name}\n'
        f'Contact ({enquiry.get_contact_kind_display()}): {enquiry.contact}\n'
        f'Language: {enquiry.locale}\n'
        f'Page: {enquiry.page or "-"}\n'
        f'Received: {enquiry.created:%Y-%m-%d %H:%M} UTC\n\n'
        f'{enquiry.message}\n\n'
        f'Reference #{enquiry.pk}. Retained until {enquiry.retention_until:%Y-%m-%d}.\n'
    )
    try:
        send_mail(subject, body, None, recipients)
    except Exception:
        # The enquiry is already stored; staff can still see it in the admin.
        logger.exception('Enquiry %s stored; staff email failed', enquiry.pk)
        return False
    logger.info('Enquiry %s (%s) stored and staff notified', enquiry.pk, enquiry.enquiry_type)
    return True
