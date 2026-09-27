"""Abstract bases shared by every content model (SITEMAP §5).

Every public content type carries `status`, `sort_order`, `created` and
`updated`. Only `status == published` rows ever leave the API.
"""

from django.db import models


class Status(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    REVIEW = 'review', 'In review'
    PUBLISHED = 'published', 'Published'


class PublishableQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Status.PUBLISHED)


class Publishable(models.Model):
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    sort_order = models.PositiveIntegerField(default=0, db_index=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    objects = PublishableQuerySet.as_manager()

    class Meta:
        abstract = True
        ordering = ['sort_order', 'pk']
