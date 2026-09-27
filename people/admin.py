from django.contrib import admin
from modeltranslation.admin import TabbedTranslationAdmin

from common.admin import PUBLISH_ACTIONS

from .models import Partner, Region, TeamMember


@admin.register(TeamMember)
class TeamMemberAdmin(TabbedTranslationAdmin):
    list_display = ('name', 'department', 'tier', 'years_experience', 'consent_to_publish', 'status')
    list_filter = ('department', 'tier', 'status', 'consent_to_publish', 'is_blog_author')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    actions = PUBLISH_ACTIONS


@admin.register(Partner)
class PartnerAdmin(TabbedTranslationAdmin):
    list_display = ('name', 'tier', 'permission_to_display', 'since_year', 'status', 'sort_order')
    list_filter = ('tier', 'status', 'permission_to_display')
    list_editable = ('sort_order',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    actions = PUBLISH_ACTIONS


@admin.register(Region)
class RegionAdmin(TabbedTranslationAdmin):
    list_display = ('name', 'key', 'geo_key', 'note', 'status', 'sort_order')
    list_filter = ('status',)
    list_editable = ('sort_order',)
    actions = PUBLISH_ACTIONS
