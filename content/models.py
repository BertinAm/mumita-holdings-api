from django.db import models
from django.utils import timezone

from common.models import Publishable, PublishableQuerySet, Status


class Lens(models.TextChoices):
    """The five specialist lenses (Review §8)."""

    HR = 'hr', 'HR'
    AGRIC_ECONOMICS = 'agric-economics', 'Agric-economics'
    NUTRITION = 'nutrition', 'Nutrition'
    FOOD_PROCESSING = 'food-processing', 'Food processing'
    IT = 'it', 'IT'


class PostQuerySet(PublishableQuerySet):
    def published(self):
        return self.filter(status=Status.PUBLISHED, published_at__lte=timezone.now())


class Post(Publishable):
    """SITEMAP §5 content.Post.

    `published_at` is the TRUE original publication date. Migrated posts keep
    their original date; never reset it to the import date.
    """

    slug = models.SlugField(max_length=120, unique=True)
    title = models.CharField(max_length=200)
    dek = models.CharField(max_length=300, blank=True, help_text='Standfirst under the title.')
    body = models.TextField(help_text='Markdown.')
    lens = models.CharField(max_length=20, choices=Lens.choices, blank=True)
    author = models.ForeignKey(
        'people.TeamMember', null=True, blank=True, on_delete=models.SET_NULL, related_name='posts'
    )
    published_at = models.DateTimeField(
        null=True, blank=True, db_index=True, help_text='True original publication date.'
    )
    media_key = models.CharField(max_length=120, blank=True, help_text='Hero image media-manifest id.')
    seo_title = models.CharField(max_length=70, blank=True)
    meta_description = models.CharField(max_length=160, blank=True)

    objects = PostQuerySet.as_manager()

    class Meta:
        ordering = ['-published_at', '-pk']

    def __str__(self):
        return self.title

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.status == Status.PUBLISHED and not self.published_at:
            raise ValidationError({'published_at': 'A published post needs its original publication date.'})


class GalleryItem(Publishable):
    """SITEMAP §5 content.GalleryItem. Group and action photographs are
    allowed here; `has_identifiable_faces` keeps them off the team page."""

    media_key = models.CharField(max_length=120, help_text='Frontend media-manifest id.')
    alt = models.CharField(max_length=200)
    caption = models.CharField(max_length=240, blank=True)
    category = models.SlugField(max_length=40, blank=True)
    place = models.CharField(max_length=120, blank=True)
    date = models.DateField(null=True, blank=True)
    has_identifiable_faces = models.BooleanField(default=False)

    class Meta(Publishable.Meta):
        pass

    def __str__(self):
        return self.media_key
