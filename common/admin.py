from django.contrib import admin

from .models import Status


@admin.action(description='Publish selected')
def make_published(modeladmin, request, queryset):
    queryset.update(status=Status.PUBLISHED)


@admin.action(description='Move selected back to draft')
def make_draft(modeladmin, request, queryset):
    queryset.update(status=Status.DRAFT)


PUBLISH_ACTIONS = [make_published, make_draft]
