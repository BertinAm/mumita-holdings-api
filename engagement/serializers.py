import re
import unicodedata

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from rest_framework import serializers

from .models import Enquiry

USER_FIELDS = ('name', 'contact', 'type', 'message')
HONEYPOT_FIELD = 'website'
PHONE_RE = re.compile(r'^\+?[\d\s().-]+$')


def clean_text(value, *, multiline=False):
    """Strip control characters (keeping newlines in multi-line fields) and
    surrounding whitespace. Output is stored as plain text and escaped
    wherever it is rendered."""
    keep = {'\n', '\t'} if multiline else set()
    value = ''.join(
        ch for ch in value
        if ch in keep or unicodedata.category(ch)[0] != 'C'
    )
    return value.replace('\r\n', '\n').strip()


class EnquirySerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100, trim_whitespace=True)
    contact = serializers.CharField(max_length=254, trim_whitespace=True)
    type = serializers.ChoiceField(choices=Enquiry.Type.choices)
    message = serializers.CharField(max_length=2000, trim_whitespace=True)

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError({'non_field_errors': ['Expected a JSON object.']})
        extra = sorted(set(data) - set(USER_FIELDS) - {HONEYPOT_FIELD})
        if extra:
            # Review §10: four fields maximum. Anything else is refused, not ignored.
            raise serializers.ValidationError(
                {key: ['Unknown field. This form accepts name, contact, type and message only.'] for key in extra}
            )
        return super().to_internal_value(data)

    def validate_name(self, value):
        value = clean_text(value)
        if len(value) < 2:
            raise serializers.ValidationError('Please enter your name.')
        return value

    def validate_message(self, value):
        value = clean_text(value, multiline=True)
        if len(value) < 2:
            raise serializers.ValidationError('Please enter a message.')
        return value

    def validate_contact(self, value):
        value = clean_text(value)
        if '@' in value:
            try:
                validate_email(value)
            except DjangoValidationError:
                raise serializers.ValidationError('Enter a valid email address or phone number.')
            self._contact_kind = Enquiry.ContactKind.EMAIL
            return value.lower()
        digits = re.sub(r'\D', '', value)
        if not PHONE_RE.match(value) or not 7 <= len(digits) <= 15:
            raise serializers.ValidationError('Enter a valid email address or phone number.')
        self._contact_kind = Enquiry.ContactKind.PHONE
        return value

    @property
    def contact_kind(self):
        return self._contact_kind
