import logging

from django.conf import settings
from django.utils.cache import patch_cache_control
from rest_framework import generics, serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.security import ClientIPScopedRateThrottle, client_ip, hash_ip

from .models import Enquiry, Testimonial
from .notify import notify_staff
from .serializers import HONEYPOT_FIELD, EnquirySerializer, TestimonialSerializer

logger = logging.getLogger(__name__)

ACCEPTED = {'ok': True}


class EnquiryView(APIView):
    """POST /api/v1/enquiries/

    Body (JSON): {"name", "contact", "type", "message"}; plus the hidden
    honeypot "website", which must be absent or empty. No cookies or session
    auth are involved, so CSRF does not apply; CORS and the Origin check below
    limit which sites can post from a browser.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ClientIPScopedRateThrottle]
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
            source=v.get('source', ''),
            topic=v.get('topic', ''),
            locale=getattr(request, 'LANGUAGE_CODE', 'en'),
            page=referer,
            ip_hash=hash_ip(client_ip(request)),
        )
        enquiry.staff_notified = notify_staff(enquiry)
        enquiry.save(update_fields=['staff_notified'])
        return Response(ACCEPTED, status=status.HTTP_201_CREATED)


class TestimonialSubmitView(APIView):
    """POST testimonials/submit/. Honeypot, throttle and Origin check as for
    enquiries. Lands as `pending`; nothing is public until an admin approves."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ClientIPScopedRateThrottle]
    throttle_scope = 'testimonials'

    def post(self, request):
        origin = request.headers.get('Origin')
        if origin and origin not in settings.CORS_ALLOWED_ORIGINS:
            return Response({'detail': 'Origin not allowed.'}, status=status.HTTP_403_FORBIDDEN)
        data = request.data
        if isinstance(data, dict) and str(data.get(HONEYPOT_FIELD) or '').strip():
            logger.info('Testimonial dropped by honeypot')
            return Response(ACCEPTED, status=status.HTTP_201_CREATED)
        serializer = TestimonialSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data
        t = Testimonial.objects.create(
            name=v['name'], role_or_place=v.get('role_or_place', ''), quote=v['quote'], consent=True,
            locale=getattr(request, 'LANGUAGE_CODE', 'en'),
            ip_hash=hash_ip(client_ip(request)),
        )
        logger.info('Testimonial %s received (pending)', t.pk)
        return Response(ACCEPTED, status=status.HTTP_201_CREATED)


class PublicTestimonialSerializer(serializers.ModelSerializer):
    photo = serializers.SerializerMethodField()

    class Meta:
        model = Testimonial
        fields = ['id', 'name', 'role_or_place', 'quote', 'photo']

    def get_photo(self, obj):
        return None  # No photos in v1 (no faces rule).


class TestimonialListView(generics.ListAPIView):
    """GET testimonials/: published (approved, consented) only."""

    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = PublicTestimonialSerializer

    def get_queryset(self):
        return Testimonial.objects.filter(status=Testimonial.State.PUBLISHED, consent=True)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        if request.method == 'GET' and response.status_code == 200:
            patch_cache_control(response, public=True, max_age=300)
        return response
