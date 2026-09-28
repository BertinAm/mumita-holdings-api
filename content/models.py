import math
import re

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.html import strip_tags

from common.models import Publishable, PublishableQuerySet


class Lens(models.TextChoices):
    """The five specialist lenses (Review §8)."""

    HR = 'hr', 'HR'
    AGRIC_ECONOMICS = 'agric-economics', 'Agric-economics'
    NUTRITION = 'nutrition', 'Nutrition'
    FOOD_PROCESSING = 'food-processing', 'Food processing'
    IT = 'it', 'IT'


class Image(models.Model):
    """An uploaded image and its renditions (PLATFORM-CONTRACT "Hosting").

    The original upload is never kept: it may carry EXIF data (GPS, camera
    serials). What is stored is re-encoded from the pixels only: AVIF and
    WebP at 400/800/1200/1600/2400 px wide (never above the source), a tiny
    blurred placeholder, and `file`, the largest WebP, used as `src`.
    """

    class Kind(models.TextChoices):
        GALLERY = 'gallery', 'Gallery photo'
        INLINE = 'inline', 'Article image'

    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.INLINE)
    file = models.FileField(upload_to='uploads/', max_length=200)
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    renditions = models.JSONField(default=list, help_text='[{"w", "fmt", "path"}], paths relative to MEDIA_ROOT.')
    blur = models.TextField(blank=True, help_text='A tiny WebP data URI for the loading placeholder.')
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created', '-pk']

    def __str__(self):
        return f'{self.get_kind_display()} #{self.pk} ({self.width}x{self.height})'

    def storage_paths(self):
        paths = {self.file.name} if self.file else set()
        paths.update(r['path'] for r in self.renditions or [])
        return paths


class PostStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    PENDING_REVIEW = 'pending_review', 'Pending review'
    CHANGES_REQUESTED = 'changes_requested', 'Changes requested'
    PUBLISHED = 'published', 'Published'


class PostQuerySet(PublishableQuerySet):
    def published(self):
        return self.filter(status=PostStatus.PUBLISHED, published_at__lte=timezone.now())


WORDS_PER_MINUTE = 200


def html_text(html):
    return re.sub(r'\s+', ' ', strip_tags(html or '').replace('&nbsp;', ' ')).strip()


def word_count(html):
    return len(html_text(html).split())


def reading_minutes(html):
    return max(1, math.ceil(word_count(html) / WORDS_PER_MINUTE))


def auto_excerpt(html, limit=200):
    text = html_text(html)
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(' ', 1)[0].rstrip(',;:.-')
    return f'{cut}…'


class PostContent(models.Model):
    """The editable fields shared by a live Post and its pending revision."""

    slug = models.SlugField(max_length=120)
    title = models.CharField(max_length=200)
    dek = models.CharField(max_length=300, blank=True, help_text='Standfirst under the title.')
    excerpt = models.CharField(max_length=300, blank=True, help_text='Card text. Computed from the body when empty.')
    body = models.TextField(blank=True, help_text='HTML, sanitized on save to the article allow-list.')
    lens = models.CharField(max_length=20, choices=Lens.choices, blank=True)
    cover = models.ForeignKey(Image, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    seo_title = models.CharField(max_length=70, blank=True)
    seo_description = models.CharField(max_length=160, blank=True)

    EDITABLE = ('slug', 'title', 'dek', 'excerpt', 'body', 'lens', 'cover', 'seo_title', 'seo_description')

    class Meta:
        abstract = True


class Post(PostContent, Publishable):
    """SITEMAP §5 content.Post, with the dashboard workflow
    (PLATFORM-CONTRACT "Post workflow"):

        draft → pending_review → published
                              ↘ changes_requested → pending_review

    `published_at` is the TRUE original publication date. Migrated posts keep
    their original date; never reset it to the import date.

    Editing a published post through write/ does not touch these fields: it
    creates a PostRevision, and the live version stays up until an admin
    approves the revision.
    """

    slug = models.SlugField(max_length=120, unique=True)
    status = models.CharField(
        max_length=20, choices=PostStatus.choices, default=PostStatus.DRAFT, db_index=True
    )
    author = models.ForeignKey(
        'people.TeamMember', null=True, blank=True, on_delete=models.SET_NULL, related_name='posts',
        help_text='Optional specialist profile (lens byline).',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='posts',
        help_text='The account that owns the article (publishers see only their own).',
    )
    byline = models.CharField(
        max_length=120, blank=True, help_text='Public author name. Empty: the owner\'s name, else "Mumita Holdings".'
    )
    published_at = models.DateTimeField(
        null=True, blank=True, db_index=True, help_text='True original publication date.'
    )
    media_key = models.CharField(
        max_length=120, blank=True, help_text='Frontend media-manifest id of the hero, for posts without a cover.'
    )
    review_note = models.TextField(blank=True, help_text='Shown to the author when changes are requested.')
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )

    objects = PostQuerySet.as_manager()

    class Meta:
        ordering = ['-published_at', '-pk']

    def __str__(self):
        return self.title

    @property
    def author_name(self):
        from accounts.auth import display_name

        if self.byline:
            return self.byline
        a = self.author
        if a and a.status == 'published' and a.consent_to_publish:
            return a.name
        if self.created_by_id:
            return display_name(self.created_by)
        return 'Mumita Holdings'

    @property
    def is_live(self):
        return self.status == PostStatus.PUBLISHED

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.status == PostStatus.PUBLISHED and not self.published_at:
            raise ValidationError({'published_at': 'A published post needs its original publication date.'})

    def save(self, *args, **kwargs):
        from .sanitize import sanitize_html

        for lang, _ in settings.LANGUAGES:
            field = f'body_{lang}'
            value = getattr(self, field, None)
            if value:
                setattr(self, field, sanitize_html(value))
        super().save(*args, **kwargs)


class PostRevision(PostContent):
    """Pending edits to a published post. At most one per post; approving it
    copies the fields onto the Post and deletes it."""

    post = models.OneToOneField(Post, on_delete=models.CASCADE, related_name='revision')
    status = models.CharField(
        max_length=20, default=PostStatus.PENDING_REVIEW,
        choices=[c for c in PostStatus.choices if c[0] != PostStatus.PUBLISHED],
    )
    review_note = models.TextField(blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Revision of {self.post}'

    def save(self, *args, **kwargs):
        from .sanitize import sanitize_html

        self.body = sanitize_html(self.body)
        super().save(*args, **kwargs)


class GalleryCategory(models.TextChoices):
    """The site's gallery keys (frontend messages/<locale>/gallery.json)."""

    FARMS = 'farms', 'Farms'
    TRAINING = 'training', 'Training'
    PROCESSING = 'processing', 'Processing'
    COLD = 'cold', 'Cold rooms'
    PRODUCTS = 'products', 'Products'
    EVENTS = 'events', 'Events'
    AWARDS = 'awards', 'Awards'
    CSR = 'csr', 'Community'
    INTERNATIONAL = 'international', 'International'
    PRAIS = 'prais', 'Praïs'


class GalleryItem(Publishable):
    """SITEMAP §5 content.GalleryItem. Group and action photographs are
    allowed here; `has_identifiable_faces` keeps them off the team page.

    Rows uploaded through the dashboard carry an `image` with renditions.
    `media_key` is for rows that point at the frontend's own media manifest."""

    image = models.ForeignKey(Image, null=True, blank=True, on_delete=models.CASCADE, related_name='gallery_items')
    media_key = models.CharField(max_length=120, blank=True, help_text='Frontend media-manifest id.')
    alt = models.CharField(max_length=200)
    caption = models.CharField(max_length=240, blank=True)
    category = models.CharField(max_length=20, choices=GalleryCategory.choices, blank=True, db_index=True)
    place = models.CharField(max_length=120, blank=True)
    date = models.DateField(null=True, blank=True)
    has_identifiable_faces = models.BooleanField(default=False)

    class Meta(Publishable.Meta):
        pass

    def __str__(self):
        return self.media_key or f'Gallery photo #{self.pk}'
