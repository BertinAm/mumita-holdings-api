from django.contrib import admin
from modeltranslation.admin import TabbedTranslationAdmin

from common.admin import PUBLISH_ACTIONS

from .models import GalleryItem, Image, Post, PostRevision


@admin.register(Post)
class PostAdmin(TabbedTranslationAdmin):
    list_display = ('title', 'lens', 'author', 'published_at', 'status')
    list_filter = ('status', 'lens', 'author')
    date_hierarchy = 'published_at'
    search_fields = ('title', 'slug', 'body')
    prepopulated_fields = {'slug': ('title',)}
    autocomplete_fields = ('author',)
    list_select_related = ('author',)
    actions = PUBLISH_ACTIONS


@admin.register(GalleryItem)
class GalleryItemAdmin(TabbedTranslationAdmin):
    list_display = ('media_key', 'category', 'place', 'date', 'has_identifiable_faces', 'status', 'sort_order')
    list_filter = ('status', 'category', 'has_identifiable_faces')
    list_editable = ('sort_order',)
    search_fields = ('media_key', 'caption', 'place')
    actions = PUBLISH_ACTIONS


@admin.register(PostRevision)
class PostRevisionAdmin(admin.ModelAdmin):
    list_display = ('post', 'status', 'created_by', 'updated')
    list_filter = ('status',)


@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'kind', 'uploaded_by', 'created')
    list_filter = ('kind',)
    readonly_fields = ('kind', 'file', 'width', 'height', 'renditions', 'blur', 'uploaded_by', 'created')

    def has_add_permission(self, request):
        return False
