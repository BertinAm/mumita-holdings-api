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
        UNREAD = 'unread', 'Unread'
        READ = 'read', 'Read'
        REPLIED = 'replied', 'Replied'
        ARCHIVED = 'archived', 'Archived'

    class Source(models.TextChoices):
        """The form that sent it, set by the page (PLATFORM-CONTRACT)."""

        CONTACT = 'contact', 'Contact'
        PARTNERS = 'partners', 'Partners'
        JOIN_DISTRIBUTOR = 'join-distributor', 'Join: distributor'
        JOIN_STRATEGIC = 'join-strategic', 'Join: strategic partner'
        JOIN_INVESTOR = 'join-investor', 'Join: investor'
        JOIN_VOLUNTEER = 'join-volunteer', 'Join: volunteer'
        JOIN_GRANT = 'join-grant', 'Join: grant'
        MARKETPLACE_REGISTER = 'marketplace-register', 'Marketplace registration'
        FEASIBILITY = 'feasibility', 'Feasibility study'
        PRODUCT_QUOTE = 'product-quote', 'Product quote'
        SERVICE_QUOTE = 'service-quote', 'Service quote'

    # The four user fields.
    name = models.CharField(max_length=100)
    contact = models.CharField(max_length=254, help_text='Email address or phone number.')
    enquiry_type = models.CharField(max_length=10, choices=Type.choices)
    message = models.TextField(max_length=2000)

    # Set by the page, not typed by the visitor.
    source = models.CharField(max_length=24, choices=Source.choices, blank=True, db_index=True)
    topic = models.CharField(max_length=120, blank=True, help_text='E.g. the product the quote is for.')

    # Server-recorded.
    contact_kind = models.CharField(max_length=5, choices=ContactKind.choices)
    locale = models.CharField(max_length=5, default='en')
    page = models.CharField(max_length=300, blank=True, help_text='Referring page, from the Referer header.')
    ip_hash = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=10, choices=State.choices, default=State.UNREAD, db_index=True)
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


class EnquiryReply(models.Model):
    """A reply sent from the dashboard. Deleted with its enquiry (retention)."""

    enquiry = models.ForeignKey(Enquiry, on_delete=models.CASCADE, related_name='replies')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    message = models.TextField(max_length=10000)
    emailed = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created', 'pk']
        verbose_name_plural = 'enquiry replies'

    def __str__(self):
        return f'Reply to enquiry #{self.enquiry_id}'


class Testimonial(models.Model):
    """A visitor testimonial (Testimonials policy: real and consented only).

    Submitted through the public form as `pending`; shown only once an admin
    publishes it. No photo field in v1 (no faces rule)."""

    class State(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PUBLISHED = 'published', 'Published'
        REJECTED = 'rejected', 'Rejected'

    name = models.CharField(max_length=100)
    role_or_place = models.CharField(max_length=120, blank=True)
    quote = models.TextField(max_length=1000)
    consent = models.BooleanField(default=False, help_text='The person agreed to have this published.')
    status = models.CharField(max_length=10, choices=State.choices, default=State.PENDING, db_index=True)
    locale = models.CharField(max_length=5, default='en')
    ip_hash = models.CharField(max_length=64, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', '-created', '-pk']

    def __str__(self):
        return f'{self.name} ({self.get_status_display()})'
