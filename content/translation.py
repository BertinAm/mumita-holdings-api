from modeltranslation.translator import TranslationOptions, register

from .models import GalleryItem, Post


@register(Post)
class PostTR(TranslationOptions):
    fields = ('title', 'dek', 'body', 'seo_title', 'meta_description')
    required_languages = ('en',)


@register(GalleryItem)
class GalleryItemTR(TranslationOptions):
    fields = ('alt', 'caption')
    required_languages = ('en',)
