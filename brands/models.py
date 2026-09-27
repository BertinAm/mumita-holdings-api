from django.core.validators import FileExtensionValidator
from django.db import models

from common.models import Publishable


class Brand(Publishable):
    """A Mumita company, or a product line under one (SITEMAP §5 brands.Brand).

    Colours are not stored here: the palette is a frontend token set keyed by
    `key` ([data-brand] in the frontend's globals.css), so the backend cannot
    drift from the approved values.
    """

    class Kind(models.TextChoices):
        COMPANY = 'company', 'Company'
        LINE = 'line', 'Product line'

    class PaletteStatus(models.TextChoices):
        APPROVED = 'approved', 'Approved'
        PROVISIONAL = 'provisional', 'Provisional'

    key = models.SlugField(
        max_length=40, unique=True,
        help_text='Frontend brand key (agro, foods, prais, marketplace). Drives [data-brand].',
    )
    slug = models.SlugField(max_length=60, unique=True, help_text='URL slug under /companies.')
    # Proper noun: not translated.
    name = models.CharField(max_length=120)
    short_name = models.CharField(max_length=60, blank=True, help_text='Capsule step title.')
    role = models.CharField(max_length=160, blank=True)
    summary = models.TextField(blank=True)
    step_body = models.TextField(blank=True)
    signoff = models.CharField(max_length=80, default='A Mumita Company')
    logo = models.FileField(
        upload_to='brands/', blank=True,
        validators=[FileExtensionValidator(['svg', 'png', 'webp'])],
    )
    palette_status = models.CharField(
        max_length=12, choices=PaletteStatus.choices, default=PaletteStatus.PROVISIONAL
    )
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.COMPANY)
    parent = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.PROTECT, related_name='lines',
        help_text='Set for product lines (LYDA and Mumi Chips sit under Mumita Foods).',
    )
    external_url = models.URLField(blank=True)

    class Meta(Publishable.Meta):
        pass

    def __str__(self):
        return self.name
