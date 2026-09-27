from django.db import models

from brands.models import Brand
from common.models import Publishable


class Product(Publishable):
    """SITEMAP §5 catalog.Product. Deliberately no price field: the client
    publishes no prices, and none may be exposed until it does."""

    class Category(models.TextChoices):
        PROCESSED = 'processed', 'Processed'
        VEGETABLE = 'vegetable', 'Vegetable'
        GRAIN = 'grain', 'Grain'
        FRESH = 'fresh', 'Fresh produce'
        EQUIPMENT = 'equipment', 'Equipment'
        PLANTING = 'planting', 'Planting material'

    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name='products')
    slug = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=12, choices=Category.choices, default=Category.PROCESSED)
    blurb = models.TextField(blank=True, help_text='One or two lines for cards.')
    description = models.TextField(blank=True)
    ingredients = models.TextField(blank=True)
    uses = models.TextField(blank=True)
    shelf_life = models.CharField(max_length=80, blank=True)
    weight = models.CharField(
        max_length=40, blank=True,
        help_text='Pack weight as printed, e.g. "300 g". Leave blank until confirmed.',
    )
    media_key = models.CharField(max_length=120, blank=True, help_text='Frontend media-manifest id.')
    cutout = models.CharField(max_length=200, blank=True, help_text='Frontend path of the cut-out pack shot.')
    alt = models.CharField(max_length=200, blank=True, help_text='Alt text for the pack shot.')
    is_on_sale = models.BooleanField(default=True)

    class Meta(Publishable.Meta):
        pass

    def __str__(self):
        return self.name


class Service(Publishable):
    """SITEMAP §5 catalog.Service. List fields are one item per line."""

    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name='services')
    slug = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    summary = models.TextField(blank=True)
    includes = models.TextField(blank=True, help_text='One item per line.')
    process_steps = models.TextField(blank=True, help_text='One step per line.')
    price_note = models.CharField(
        max_length=160, blank=True, help_text='e.g. a published fee range. Leave blank if unconfirmed.'
    )
    media_key = models.CharField(max_length=120, blank=True)

    class Meta(Publishable.Meta):
        pass

    def __str__(self):
        return self.name
