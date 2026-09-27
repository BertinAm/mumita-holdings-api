from modeltranslation.translator import TranslationOptions, register

from .models import Partner, Region, TeamMember


@register(TeamMember)
class TeamMemberTR(TranslationOptions):
    # Names are proper nouns and stay untranslated.
    fields = ('qualification', 'value_statement')


@register(Partner)
class PartnerTR(TranslationOptions):
    fields = ('relationship',)


@register(Region)
class RegionTR(TranslationOptions):
    fields = ('name', 'note')
    required_languages = ('en',)
