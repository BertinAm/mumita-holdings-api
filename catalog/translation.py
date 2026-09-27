from modeltranslation.translator import TranslationOptions, register

from .models import Product, Service


@register(Product)
class ProductTR(TranslationOptions):
    fields = ('name', 'blurb', 'description', 'ingredients', 'uses', 'shelf_life', 'alt')
    required_languages = ('en',)


@register(Service)
class ServiceTR(TranslationOptions):
    fields = ('name', 'summary', 'includes', 'process_steps', 'price_note')
    required_languages = ('en',)
