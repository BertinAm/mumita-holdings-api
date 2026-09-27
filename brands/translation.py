from modeltranslation.translator import TranslationOptions, register

from .models import Brand


@register(Brand)
class BrandTR(TranslationOptions):
    fields = ('short_name', 'role', 'summary', 'step_body', 'signoff')
