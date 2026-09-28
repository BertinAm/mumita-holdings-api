"""manage/posts, write/posts, manage/gallery and the inline uploads.

A post is always shown as its *working copy*: the pending revision when a
published post has one, else the post itself. `status` is the working
copy's status; `has_live_version` says whether a published version is up.
"""

import logging

from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.auth import DashboardSessionAuthentication, IsAdmin, IsWriter, display_name, role_of
from accounts.models import Realm
from accounts.views import admin_emails
from common import revalidate
from common.mail import send_email
from common.pagination import DashboardPagination

from .images import ImageError, create_image, image_payload
from .models import (
    GalleryCategory, GalleryItem, Image, Lens, Post, PostRevision, PostStatus, auto_excerpt, reading_minutes,
    word_count,
)

logger = logging.getLogger('content')

PUBLISHED = PostStatus.PUBLISHED
PENDING = PostStatus.PENDING_REVIEW
CHANGES = PostStatus.CHANGES_REQUESTED
DRAFT = PostStatus.DRAFT


def revision_of(post):
    try:
        return post.revision
    except PostRevision.DoesNotExist:
        return None


def working_copy(post):
    return revision_of(post) or post


def post_payload(post, request, *, full=True):
    rev = revision_of(post)
    src = rev or post
    data = {
        'id': post.pk,
        'slug': src.slug,
        'title': src.title,
        'dek': src.dek,
        'excerpt': src.excerpt,
        'excerpt_auto': auto_excerpt(src.body),
        'lens': src.lens,
        'cover': image_payload(src.cover, request),
        'seo_title': src.seo_title,
        'seo_description': src.seo_description,
        'status': src.status,
        'review_note': src.review_note,
        'has_live_version': post.status == PUBLISHED,
        'has_pending_revision': rev is not None,
        'live_slug': post.slug if post.status == PUBLISHED else None,
        'author': post.author_name,
        'owner': {'id': post.created_by_id, 'name': display_name(post.created_by)} if post.created_by_id else None,
        'byline': post.byline,
        'media_key': post.media_key,
        'published_at': post.published_at,
        'submitted_at': src.submitted_at,
        'created': post.created,
        'updated': max(post.updated, rev.updated) if rev else post.updated,
        'word_count': word_count(src.body),
        'reading_minutes': reading_minutes(src.body),
    }
    if full:
        data['body_html'] = src.body
    return data


def unique_slug(base, *, exclude_pk=None):
    base = (slugify(base) or 'post')[:100].strip('-') or 'post'
    slug, n = base, 2
    qs = Post.objects.exclude(pk=exclude_pk) if exclude_pk else Post.objects.all()
    while qs.filter(slug=slug).exists():
        slug = f'{base}-{n}'
        n += 1
    return slug


class PostInputSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, required=False)
    slug = serializers.CharField(max_length=120, required=False, allow_blank=True)
    dek = serializers.CharField(max_length=300, required=False, allow_blank=True)
    excerpt = serializers.CharField(max_length=300, required=False, allow_blank=True)
    body_html = serializers.CharField(max_length=500_000, required=False, allow_blank=True, trim_whitespace=False)
    lens = serializers.ChoiceField(choices=Lens.choices, required=False, allow_blank=True)
    cover_id = serializers.IntegerField(required=False, allow_null=True)
    seo_title = serializers.CharField(max_length=70, required=False, allow_blank=True)
    seo_description = serializers.CharField(max_length=160, required=False, allow_blank=True)

    def __init__(self, *args, post=None, user=None, **kwargs):
        self.post = post
        self.user = user
        super().__init__(*args, **kwargs)

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = sorted(set(data) - set(self.fields))
            if unknown:
                raise ValidationError({key: ['Unknown or read-only field.'] for key in unknown})
        return super().to_internal_value(data)

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Enter a title.')
        return value

    def validate_slug(self, value):
        if not value:
            return value
        slug = slugify(value)[:120]
        if not slug:
            raise serializers.ValidationError('Use letters, numbers and hyphens.')
        clash = Post.objects.filter(slug=slug)
        if self.post:
            clash = clash.exclude(pk=self.post.pk)
        if clash.exists():
            raise serializers.ValidationError('Another article already uses this address.')
        return slug

    def validate_cover_id(self, value):
        if value is None:
            return None
        image = Image.objects.filter(pk=value).first()
        if image is None:
            raise serializers.ValidationError('Unknown image.')
        if role_of(self.user) != Realm.ADMIN:
            current = working_copy(self.post).cover_id if self.post else None
            if image.uploaded_by_id != self.user.pk and image.pk != current:
                raise serializers.ValidationError('Use an image you uploaded.')
        return value

    def validate(self, attrs):
        if self.post is None and not attrs.get('title'):
            raise ValidationError({'title': ['Enter a title.']})
        return attrs

    def content_fields(self):
        """validated_data mapped onto model field names."""
        out = {}
        for key, value in self.validated_data.items():
            if key == 'body_html':
                out['body'] = value
            elif key == 'cover_id':
                out['cover_id'] = value
            elif key in Post.EDITABLE:
                out[key] = value
        if 'slug' in out and not out['slug']:
            del out['slug']
        return out


class AdminPostInputSerializer(PostInputSerializer):
    status = serializers.ChoiceField(choices=PostStatus.choices, required=False)
    published_at = serializers.DateTimeField(required=False, allow_null=True)
    byline = serializers.CharField(max_length=120, required=False, allow_blank=True)
    media_key = serializers.CharField(max_length=120, required=False, allow_blank=True)


def apply(target, fields):
    for key, value in fields.items():
        setattr(target, key, value)


def copy_content(source, target):
    for key in Post.EDITABLE:
        if key == 'cover':
            target.cover_id = source.cover_id
        else:
            setattr(target, key, getattr(source, key))


def start_revision(post, user):
    rev = PostRevision(post=post, created_by=user, status=PENDING)
    copy_content(post, rev)
    return rev


def publish(post, reviewer, *, published_at=None):
    """Publish the working copy. Returns the paths to revalidate."""
    rev = revision_of(post)
    old_slug = post.slug if post.status == PUBLISHED else None
    if rev is not None:
        copy_content(rev, post)
        rev.delete()
    post.status = PUBLISHED
    if published_at:
        post.published_at = published_at
    elif not post.published_at:
        post.published_at = timezone.now()
    post.review_note = ''
    post.reviewed_by = reviewer
    post.reviewed_at = timezone.now()
    post.save()
    post._state.fields_cache.pop('revision', None)
    paths = revalidate.post_paths(old_slug, post.slug)
    revalidate.revalidate(paths)
    logger.info('Post %s published by user %s', post.pk, reviewer.pk if reviewer else None)
    return paths


def unpublish(post, new_status):
    """Take a published post down; a pending revision becomes the post."""
    rev = revision_of(post)
    old_slug = post.slug
    if rev is not None:
        copy_content(rev, post)
        post.review_note = rev.review_note
        post.submitted_at = rev.submitted_at
        rev.delete()
        post._state.fields_cache.pop('revision', None)
    post.status = new_status
    post.save()
    revalidate.revalidate(revalidate.post_paths(old_slug, post.slug))
    logger.info('Post %s unpublished (%s)', post.pk, new_status)


def notify_submitted(post, user):
    src = working_copy(post)
    from django.conf import settings

    send_email(
        admin_emails(), f'Article for review: {src.title}', 'post_submitted',
        {'author': display_name(user), 'title': src.title,
         'review_url': f'{settings.FRONTEND_URL}/dashboard/posts/{post.pk}'},
    )


def notify_changes_requested(post, note):
    from django.conf import settings

    owner = post.created_by
    if not owner or not owner.email:
        return False
    src = working_copy(post)
    return send_email(
        [owner.email], f'Changes requested: {src.title}', 'post_changes_requested',
        {'name': display_name(owner), 'title': src.title, 'note': note,
         'edit_url': f'{settings.FRONTEND_URL}/write/posts/{post.pk}'},
    )


class _PostViewSetBase(viewsets.ViewSet):
    authentication_classes = [DashboardSessionAuthentication]
    pagination_class = DashboardPagination

    def base_queryset(self):
        raise NotImplementedError

    def queryset(self):
        qs = self.base_queryset().select_related('created_by__profile', 'cover', 'author', 'revision__cover')
        params = self.request.query_params
        st = params.get('status')
        if st in PostStatus.values:
            if st == PUBLISHED:
                qs = qs.filter(status=PUBLISHED, revision__isnull=True)
            else:
                qs = qs.filter(Q(revision__status=st) | Q(revision__isnull=True, status=st))
        if params.get('live') in ('1', 'true'):
            qs = qs.filter(status=PUBLISHED)
        if params.get('lens') in Lens.values:
            qs = qs.filter(Q(revision__lens=params['lens']) | Q(revision__isnull=True, lens=params['lens']))
        q = (params.get('q') or '').strip()
        if q:
            qs = qs.filter(Q(title_en__icontains=q) | Q(slug__icontains=q) | Q(revision__title__icontains=q))
        return qs.order_by('-updated', '-pk')

    def get_post(self, pk):
        try:
            return self.base_queryset().select_related('created_by__profile').get(pk=pk)
        except (Post.DoesNotExist, ValueError, TypeError):
            from django.http import Http404

            raise Http404

    def list(self, request):
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(self.queryset(), request, view=self)
        return paginator.get_paginated_response([post_payload(p, request, full=False) for p in page])

    def retrieve(self, request, pk=None):
        return Response(post_payload(self.get_post(pk), request))

    def destroy(self, request, pk=None):
        post = self.get_post(pk)
        was_live = post.status == PUBLISHED
        slug = post.slug
        with transaction.atomic():
            post.delete()
            if was_live:
                revalidate.revalidate(revalidate.post_paths(slug))
        logger.info('Post %s deleted by user %s', pk, request.user.pk)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _create(self, request, serializer_class):
        s = serializer_class(data=request.data, user=request.user)
        s.is_valid(raise_exception=True)
        fields = s.content_fields()
        post = Post(created_by=request.user, status=DRAFT)
        apply(post, fields)
        if not fields.get('slug'):
            post.slug = unique_slug(fields['title'])
        return post, s


class WritePostViewSet(_PostViewSetBase):
    """write/posts: a publisher's (or admin's) own articles."""

    permission_classes = [IsWriter]

    def base_queryset(self):
        return Post.objects.filter(created_by=self.request.user)

    def create(self, request):
        post, _ = self._create(request, PostInputSerializer)
        post.save()
        return Response(post_payload(post, request), status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        post = self.get_post(pk)
        s = PostInputSerializer(data=request.data, post=post, user=request.user, partial=True)
        s.is_valid(raise_exception=True)
        fields = s.content_fields()
        with transaction.atomic():
            if post.status == PUBLISHED:
                # The live version stays up; the edit waits for approval.
                rev = revision_of(post) or start_revision(post, request.user)
                apply(rev, fields)
                rev.save()
                post.revision = rev
            else:
                apply(post, fields)
                post.save()
        return Response(post_payload(post, request))

    def update(self, request, pk=None):
        return self.partial_update(request, pk)

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        post = self.get_post(pk)
        target = working_copy(post)
        if target is post and post.status == PUBLISHED:
            raise ValidationError({'detail': 'This article is published. Edit it to propose changes.'})
        if not target.title or not target.body.strip():
            raise ValidationError({'detail': 'Add a title and some text before submitting.'})
        target.status = PENDING
        target.submitted_at = timezone.now()
        target.save()
        transaction.on_commit(lambda: notify_submitted(post, request.user))
        logger.info('Post %s submitted for review by user %s', post.pk, request.user.pk)
        return Response(post_payload(post, request))


class ManagePostViewSet(_PostViewSetBase):
    """manage/posts: every article; admins edit, publish, approve, reject."""

    permission_classes = [IsAdmin]

    def base_queryset(self):
        return Post.objects.all()

    def queryset(self):
        qs = super().queryset()
        author = self.request.query_params.get('owner')
        if author and author.isdigit():
            qs = qs.filter(created_by_id=int(author))
        return qs

    def create(self, request):
        post, s = self._create(request, AdminPostInputSerializer)
        v = s.validated_data
        for key in ('byline', 'media_key'):
            if key in v:
                setattr(post, key, v[key])
        if v.get('published_at'):
            post.published_at = v['published_at']
        target_status = v.get('status', DRAFT)
        with transaction.atomic():
            if target_status == PUBLISHED:
                post.save()
                publish(post, request.user, published_at=v.get('published_at'))
            else:
                post.status = target_status
                post.save()
        return Response(post_payload(post, request), status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        post = self.get_post(pk)
        s = AdminPostInputSerializer(data=request.data, post=post, user=request.user, partial=True)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        fields = s.content_fields()
        new_status = v.get('status')
        with transaction.atomic():
            rev = revision_of(post)
            live_before = post.status == PUBLISHED
            old_slug = post.slug
            if rev is not None:
                apply(rev, fields)
                rev.save()
            else:
                apply(post, fields)
            for key in ('byline', 'media_key'):
                if key in v:
                    setattr(post, key, v[key])
            if 'published_at' in v and v['published_at']:
                post.published_at = v['published_at']
            post.save()
            if new_status == PUBLISHED and (not live_before or rev is not None):
                publish(post, request.user, published_at=v.get('published_at'))
            elif new_status and new_status != PUBLISHED and live_before:
                unpublish(post, new_status)
            elif new_status and not live_before:
                post.status = new_status
                post.save(update_fields=['status', 'updated'])
            elif live_before and rev is None and (fields or 'byline' in v or 'published_at' in v):
                # A direct edit of the live version.
                revalidate.revalidate(revalidate.post_paths(old_slug, post.slug))
        post = self.get_post(pk)
        return Response(post_payload(post, request))

    def update(self, request, pk=None):
        return self.partial_update(request, pk)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        post = self.get_post(pk)
        if post.status == PUBLISHED and revision_of(post) is None:
            raise ValidationError({'detail': 'This article is already published.'})
        with transaction.atomic():
            publish(post, request.user)
        return Response(post_payload(self.get_post(pk), request))

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        post = self.get_post(pk)
        note = request.data.get('note') if isinstance(request.data, dict) else None
        note = (note or '').strip() if isinstance(note, str) else ''
        if not note:
            raise ValidationError({'note': ['Say what needs to change.']})
        if len(note) > 4000:
            raise ValidationError({'note': ['Keep the note under 4000 characters.']})
        target = working_copy(post)
        if target.status != PENDING:
            raise ValidationError({'detail': 'Only an article pending review can be sent back.'})
        target.status = CHANGES
        target.review_note = note
        target.save()
        if target is post:
            post.reviewed_by = request.user
            post.reviewed_at = timezone.now()
            post.save(update_fields=['reviewed_by', 'reviewed_at'])
        transaction.on_commit(lambda: notify_changes_requested(post, note))
        logger.info('Post %s sent back for changes by user %s', post.pk, request.user.pk)
        return Response(post_payload(post, request))


# --- uploads and gallery -----------------------------------------------------

def upload_from(request):
    upload = request.FILES.get('image')
    if upload is None:
        raise ValidationError({'image': ['Attach an image file.']})
    return upload


class _UploadView(APIView):
    authentication_classes = [DashboardSessionAuthentication]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        try:
            image = create_image(upload_from(request), kind=Image.Kind.INLINE, user=request.user)
        except ImageError as exc:
            raise ValidationError({'image': [str(exc)]})
        return Response(image_payload(image, request), status=status.HTTP_201_CREATED)


class ManageUploadView(_UploadView):
    permission_classes = [IsAdmin]


class WriteUploadView(_UploadView):
    permission_classes = [IsWriter]


GALLERY_PATHS = [revalidate.GALLERY, revalidate.HOME]


def gallery_payload(item, request):
    return {
        'id': item.pk,
        'category': item.category,
        'alt': item.alt,
        'caption': item.caption,
        'image': image_payload(item.image, request),
        'status': item.status,
        'sort_order': item.sort_order,
        'created': item.created,
        'updated': item.updated,
    }


class GalleryInputSerializer(serializers.Serializer):
    category = serializers.ChoiceField(choices=GalleryCategory.choices)
    alt = serializers.CharField(max_length=200)
    caption = serializers.CharField(max_length=240, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=['draft', 'published'], required=False)

    def validate_alt(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Describe the photo for people who cannot see it.')
        return value


class ManageGalleryViewSet(viewsets.ViewSet):
    authentication_classes = [DashboardSessionAuthentication]
    permission_classes = [IsAdmin]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    pagination_class = DashboardPagination

    def get_item(self, pk):
        from django.shortcuts import get_object_or_404

        return get_object_or_404(GalleryItem.objects.select_related('image'), pk=pk)

    def list(self, request):
        qs = GalleryItem.objects.select_related('image').order_by('sort_order', 'pk')
        category = request.query_params.get('category')
        if category in GalleryCategory.values:
            qs = qs.filter(category=category)
        st = request.query_params.get('status')
        if st in ('draft', 'published'):
            qs = qs.filter(status=st)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([gallery_payload(i, request) for i in page])

    def retrieve(self, request, pk=None):
        return Response(gallery_payload(self.get_item(pk), request))

    def create(self, request):
        s = GalleryInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        upload = upload_from(request)
        try:
            image = create_image(upload, kind=Image.Kind.GALLERY, user=request.user)
        except ImageError as exc:
            raise ValidationError({'image': [str(exc)]})
        v = s.validated_data
        with transaction.atomic():
            last = GalleryItem.objects.aggregate(m=Max('sort_order'))['m']
            item = GalleryItem.objects.create(
                image=image, category=v['category'], alt=v['alt'], caption=v.get('caption', ''),
                status=v.get('status', 'published'), sort_order=(last or 0) + 1,
            )
            revalidate.revalidate(GALLERY_PATHS)
        return Response(gallery_payload(item, request), status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        item = self.get_item(pk)
        s = GalleryInputSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        with transaction.atomic():
            for key, value in s.validated_data.items():
                setattr(item, key, value)
            item.save()
            revalidate.revalidate(GALLERY_PATHS)
        return Response(gallery_payload(item, request))

    def update(self, request, pk=None):
        return self.partial_update(request, pk)

    def destroy(self, request, pk=None):
        item = self.get_item(pk)
        with transaction.atomic():
            image = item.image
            item.delete()
            if image is not None and not image.gallery_items.exists():
                image.delete()
            revalidate.revalidate(GALLERY_PATHS)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['post'])
    def reorder(self, request):
        ids = request.data.get('ids') if isinstance(request.data, dict) else None
        if not isinstance(ids, list) or not ids or not all(isinstance(i, int) for i in ids):
            raise ValidationError({'ids': ['Send the gallery ids in their new order.']})
        if len(set(ids)) != len(ids):
            raise ValidationError({'ids': ['Each id once.']})
        items = {i.pk: i for i in GalleryItem.objects.filter(pk__in=ids)}
        missing = [i for i in ids if i not in items]
        if missing:
            raise ValidationError({'ids': [f'Unknown ids: {missing}']})
        with transaction.atomic():
            for order, pk in enumerate(ids, start=1):
                items[pk].sort_order = order
            GalleryItem.objects.bulk_update(items.values(), ['sort_order'])
            revalidate.revalidate(GALLERY_PATHS)
        return Response({'ok': True})
