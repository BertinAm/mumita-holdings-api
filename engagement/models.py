from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class Enquiry(models.Model):
    """A visitor enquiry (Review §10: four user fields, no more).

    The four user fields are name, contact, enquiry_type and message.
    Everything else is recorded by the server. The visitor's IP is never
    stored: only a keyed hash, for abuse investigation.
    Rows past `retention_until` are removed by `manage.py purge_enquiries`.
    """

    class Type(models.TextChoices):
        BUY = 'buy', 'Buy'
        FARM = 'farm', 'Farm with us'
        PARTNER = 'partner', 'Partner'
        OTHER = 'other', 'Other'

    class ContactKind(models.TextChoices):
        EMAIL = 'email', 'Email'
        PHONE = 'phone', 'Phone'

    class State(models.TextChoices):
        NEW = 'new', 'New'
        ASSIGNED = 'assigned', 'Assigned'
        CLOSED = 'closed', 'Closed'

    # The four user fields.
    name = models.CharField(max_length=100)
    contact = models.CharField(max_length=254, help_text='Email address or phone number.')
    enquiry_type = models.CharField(max_length=10, choices=Type.choices)
    message = models.TextField(max_length=2000)

    # Server-recorded.
    contact_kind = models.CharField(max_length=5, choices=ContactKind.choices)
    locale = models.CharField(max_length=5, default='en')
    page = models.CharField(max_length=300, blank=True, help_text='Referring page, from the Referer header.')
    ip_hash = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=10, choices=State.choices, default=State.NEW, db_index=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    staff_notified = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    retention_until = models.DateField(db_index=True)

    class Meta:
        ordering = ['-created']
        verbose_name_plural = 'enquiries'

    def __str__(self):
        return f'{self.get_enquiry_type_display()} enquiry #{self.pk}'

    def save(self, *args, **kwargs):
        if not self.retention_until:
            self.retention_until = (timezone.now() + timedelta(days=settings.ENQUIRY_RETENTION_DAYS)).date()
        super().save(*args, **kwargs)
