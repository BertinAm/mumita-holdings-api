"""manage/enquiries (the inbox) and manage/testimonials."""

import logging

from django.db import transaction
from django.db.models import Max, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from accounts.auth import DashboardSessionAuthentication, IsAdmin, display_name
from common import revalidate
from common.mail import send_email
from common.pagination import DashboardPagination

from .models import Enquiry, EnquiryReply, Testimonial
from .serializers import clean_text

logger = logging.getLogger('engagement')


class ReplySerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()

    class Meta:
        model = EnquiryReply
        fields = ['id', 'author', 'message', 'emailed', 'created']

    def get_author(self, obj):
        return {'id': obj.author_id, 'name': display_name(obj.author)} if obj.author_id else None


class EnquirySerializer(serializers.ModelSerializer):
    type = serializers.CharField(source='enquiry_type', read_only=True)
    replies = ReplySerializer(many=True, read_only=True)

    class Meta:
        model = Enquiry
        fields = [
            'id', 'name', 'contact', 'contact_kind', 'type', 'message', 'source', 'topic', 'locale', 'page',
            'status', 'created', 'retention_until', 'replies',
        ]
        read_only_fields = [f for f in fields if f != 'status']


class EnquiryListSerializer(EnquirySerializer):
    reply_count = serializers.IntegerField(source='replies.count', read_only=True)

    class Meta(EnquirySerializer.Meta):
        fields = [f for f in EnquirySerializer.Meta.fields if f != 'replies'] + ['reply_count']
        read_only_fields = fields


class ManageEnquiryViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                           viewsets.GenericViewSet):
    """GET manage/enquiries/?source=&status=&q=, GET/PATCH {id} (status),
    POST {id}/reply/ {message}. Enquiries are visitor data: nothing but the
    status is editable, and there is no delete (retention does that)."""

    authentication_classes = [DashboardSessionAuthentication]
    permission_classes = [IsAdmin]
    pagination_class = DashboardPagination
    http_method_names = ['get', 'patch', 'post', 'head', 'options']

    def get_serializer_class(self):
        return EnquiryListSerializer if self.action == 'list' else EnquirySerializer

    def get_queryset(self):
        qs = Enquiry.objects.prefetch_related('replies__author__profile')
        params = self.request.query_params
        if params.get('source') in Enquiry.Source.values:
            qs = qs.filter(source=params['source'])
        elif params.get('source') == 'none':
            qs = qs.filter(source='')
        if params.get('status') in Enquiry.State.values:
            qs = qs.filter(status=params['status'])
        if params.get('type') in Enquiry.Type.values:
            qs = qs.filter(enquiry_type=params['type'])
        q = (params.get('q') or '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(contact__icontains=q) | Q(message__icontains=q)
                           | Q(topic__icontains=q))
        return qs

    def retrieve(self, request, *args, **kwargs):
        enquiry = self.get_object()
        if enquiry.status == Enquiry.State.UNREAD:
            enquiry.status = Enquiry.State.READ
            enquiry.save(update_fields=['status'])
        return Response(EnquirySerializer(enquiry).data)

    def update(self, request, *args, **kwargs):
        enquiry = self.get_object()
        value = request.data.get('status') if isinstance(request.data, dict) else None
        if value not in Enquiry.State.values:
            raise ValidationError({'status': [f'One of: {", ".join(Enquiry.State.values)}.']})
        extra = set(request.data) - {'status'}
        if extra:
            raise ValidationError({key: ['Read-only field.'] for key in sorted(extra)})
        enquiry.status = value
        enquiry.save(update_fields=['status'])
        return Response(EnquirySerializer(enquiry).data)

    @action(detail=True, methods=['post'])
    def reply(self, request, pk=None):
        enquiry = self.get_object()
        message = request.data.get('message') if isinstance(request.data, dict) else None
        message = clean_text(message, multiline=True) if isinstance(message, str) else ''
        if len(message) < 2:
            raise ValidationError({'message': ['Write a reply.']})
        if len(message) > 10000:
            raise ValidationError({'message': ['Keep the reply under 10,000 characters.']})
        if enquiry.contact_kind != Enquiry.ContactKind.EMAIL:
            # The dashboard shows the number to call instead.
            return Response({'detail': 'phone'}, status=status.HTTP_400_BAD_REQUEST)
        sender = display_name(request.user)
        sent = send_email(
            [enquiry.contact], 'Re: your message to Mumita Holdings', 'enquiry_reply',
            {'name': enquiry.name, 'message': message, 'sender': sender,
             'received': enquiry.created, 'original': enquiry.message},
            reply_to=[request.user.email] if request.user.email else None,
        )
        if not sent:
            return Response({'detail': 'The email could not be sent. Try again later.'},
                            status=status.HTTP_502_BAD_GATEWAY)
        with transaction.atomic():
            reply = EnquiryReply.objects.create(enquiry=enquiry, author=request.user, message=message, emailed=True)
            enquiry.status = Enquiry.State.REPLIED
            enquiry.save(update_fields=['status'])
        logger.info('Enquiry %s replied to by user %s', enquiry.pk, request.user.pk)
        return Response(ReplySerializer(reply).data, status=status.HTTP_201_CREATED)


class ManageTestimonialSerializer(serializers.ModelSerializer):
    class Meta:
        model = Testimonial
        fields = ['id', 'name', 'role_or_place', 'quote', 'consent', 'status', 'locale', 'sort_order',
                  'created', 'updated', 'reviewed_at']
        read_only_fields = ['id', 'locale', 'created', 'updated', 'reviewed_at']

    def validate_name(self, value):
        value = clean_text(value)
        if len(value) < 2:
            raise serializers.ValidationError('Enter the person\'s name.')
        return value

    def validate_quote(self, value):
        value = clean_text(value, multiline=True)
        if len(value) < 2:
            raise serializers.ValidationError('Enter the quote.')
        return value

    def validate(self, attrs):
        consent = attrs.get('consent', self.instance.consent if self.instance else False)
        status_ = attrs.get('status', self.instance.status if self.instance else Testimonial.State.PENDING)
        if status_ == Testimonial.State.PUBLISHED and not consent:
            raise ValidationError({'consent': ['A testimonial is published only with the person\'s consent.']})
        return attrs


TESTIMONIAL_PATHS = [revalidate.HOME]


class ManageTestimonialViewSet(viewsets.ModelViewSet):
    authentication_classes = [DashboardSessionAuthentication]
    permission_classes = [IsAdmin]
    pagination_class = DashboardPagination
    serializer_class = ManageTestimonialSerializer

    def get_queryset(self):
        qs = Testimonial.objects.all()
        if self.request.query_params.get('status') in Testimonial.State.values:
            qs = qs.filter(status=self.request.query_params['status'])
        return qs

    def perform_create(self, serializer):
        last = Testimonial.objects.aggregate(m=Max('sort_order'))['m'] or 0
        serializer.save(sort_order=serializer.validated_data.get('sort_order') or last + 1)
        revalidate.revalidate(TESTIMONIAL_PATHS)

    def perform_update(self, serializer):
        serializer.save()
        revalidate.revalidate(TESTIMONIAL_PATHS)

    def perform_destroy(self, instance):
        instance.delete()
        revalidate.revalidate(TESTIMONIAL_PATHS)

    def _review(self, request, new_status):
        t = get_object_or_404(Testimonial, pk=self.kwargs['pk'])
        if new_status == Testimonial.State.PUBLISHED and not t.consent:
            raise ValidationError({'consent': ['A testimonial is published only with the person\'s consent.']})
        t.status = new_status
        t.reviewed_by = request.user
        t.reviewed_at = timezone.now()
        t.save()
        revalidate.revalidate(TESTIMONIAL_PATHS)
        return Response(ManageTestimonialSerializer(t).data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        return self._review(request, Testimonial.State.PUBLISHED)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        return self._review(request, Testimonial.State.REJECTED)
