from django.contrib import admin
from modeltranslation.admin import TabbedTranslationAdmin

from common.admin import PUBLISH_ACTIONS

from .models import Brand


@admin.register(Brand)
class BrandAdmin(TabbedTranslationAdmin):
    list_display = ('name', 'key', 'kind', 'parent', 'palette_status', 'status', 'sort_order')
    list_filter = ('kind', 'status', 'palette_status')
    list_editable = ('sort_order',)
    search_fields = ('name', 'key', 'slug')
    prepopulated_fields = {'slug': ('key',)}
    actions = PUBLISH_ACTIONS
