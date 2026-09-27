import hashlib
import hmac
import logging

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import Enquiry
from .notify import notify_staff
from .serializers import HONEYPOT_FIELD, EnquirySerializer

logger = logging.getLogger(__name__)

ACCEPTED = {'ok': True}


def hash_ip(ip):
    if not ip:
        return ''
    return hmac.new(settings.SECRET_KEY.encode(), ip.encode(), hashlib.sha256).hexdigest()


class EnquiryView(APIView):
    """POST /api/v1/enquiries/

    Body (JSON): {"name", "contact", "type", "message"}; plus the hidden
    honeypot "website", which must be absent or empty. No cookies or session
    auth are involved, so CSRF does not apply; CORS and the Origin check below
    limit which sites can post from a browser.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'enquiries'

    def post(self, request):
        origin = request.headers.get('Origin')
        if origin and origin not in settings.CORS_ALLOWED_ORIGINS:
            return Response({'detail': 'Origin not allowed.'}, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        if isinstance(data, dict) and str(data.get(HONEYPOT_FIELD) or '').strip():
            # Look identical to success so bots learn nothing. Nothing stored or sent.
            logger.info('Enquiry dropped by honeypot')
            return Response(ACCEPTED, status=status.HTTP_201_CREATED)

        serializer = EnquirySerializer(data=data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data
        referer = request.headers.get('Referer', '')[:300]
        enquiry = Enquiry.objects.create(
            name=v['name'],
            contact=v['contact'],
            contact_kind=serializer.contact_kind,
            enquiry_type=v['type'],
            message=v['message'],
            locale=getattr(request, 'LANGUAGE_CODE', 'en'),
            page=referer,
            ip_hash=hash_ip(ScopedRateThrottle().get_ident(request)),
        )
        enquiry.staff_notified = notify_staff(enquiry)
        enquiry.save(update_fields=['staff_notified'])
        return Response(ACCEPTED, status=status.HTTP_201_CREATED)
