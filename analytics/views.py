"""POST analytics/hit/ (server-to-server from the frontend Worker) and
GET manage/stats/ (the dashboard's numbers)."""

import hmac
import re
from datetime import datetime, time, timedelta
from datetime import timezone as dt_timezone
from urllib.parse import urlsplit

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.auth import DashboardSessionAuthentication, IsAdmin
from accounts.models import LoginEvent, Realm
from content.models import GalleryCategory, GalleryItem, Post, PostRevision, PostStatus
from engagement.models import Enquiry, Testimonial

from .models import DailyVisit, Device

COUNTRY_RE = re.compile(r'^[A-Z]{2}$')
HOST_RE = re.compile(r'^[a-z0-9.-]{1,120}$')
PATH_RE = re.compile(r'^/[^\s]*$')


def clean_path(value):
    if not isinstance(value, str):
        return None
    path = urlsplit(value.strip()).path or ''
    if not PATH_RE.match(path) or len(path) > 300:
        return None
    if len(path) > 1:
        path = path.rstrip('/')
    return path


def clean_host(value):
    if not value or not isinstance(value, str):
        return ''
    value = value.strip().lower()
    if '://' in value:
        value = urlsplit(value).hostname or ''
    value = value.split(':')[0]
    if value.startswith('www.'):
        value = value[4:]
    return value if HOST_RE.match(value) else ''


class HitView(APIView):
    """{path, referrer_host, country, device, is_bot} with header
    X-Analytics-Key. Bots are dropped. Answers 204."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        key = settings.ANALYTICS_INGEST_KEY
        given = request.headers.get('X-Analytics-Key', '')
        if not key or not hmac.compare_digest(given.encode(), key.encode()):
            return Response({'detail': 'Forbidden.'}, status=status.HTTP_403_FORBIDDEN)
        data = request.data if isinstance(request.data, dict) else {}
        if data.get('is_bot'):
            return Response(status=status.HTTP_204_NO_CONTENT)
        path = clean_path(data.get('path'))
        device = data.get('device')
        if path is None or device not in Device.values:
            return Response({'detail': 'Send path and device.'}, status=status.HTTP_400_BAD_REQUEST)
        country = str(data.get('country') or '').strip().upper()
        country = country if COUNTRY_RE.match(country) and country not in ('XX', 'T1') else ''
        referrer = clean_host(data.get('referrer_host'))
        key_fields = {
            'date': timezone.now().date(), 'path': path, 'country': country,
            'referrer_host': referrer, 'device': device,
        }
        updated = DailyVisit.objects.filter(**key_fields).update(views=F('views') + 1)
        if not updated:
            try:
                with transaction.atomic():
                    DailyVisit.objects.create(views=1, **key_fields)
            except IntegrityError:  # created concurrently
                DailyVisit.objects.filter(**key_fields).update(views=F('views') + 1)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _series(start_date, days, rows, keys):
    by_date = {row['day']: row for row in rows}
    out = []
    for i in range(days):
        day = start_date + timedelta(days=i)
        row = by_date.get(day, {})
        out.append({'date': day.isoformat(), **{k: row.get(k) or 0 for k in keys}})
    return out


def _months(today, count=12):
    """The first day of each of the last `count` months, oldest first."""
    year, month = today.year, today.month
    out = []
    for _ in range(count):
        out.append(today.replace(year=year, month=month, day=1))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return out[::-1]


def _keyed(values, rows, field):
    """[{field: v, count}] for every value in `values`, zero-filled."""
    counts = {row[field]: row['count'] for row in rows}
    return [{field: v, 'count': counts.get(v, 0)} for v in values]


def _top(qs, field, label, limit=10):
    rows = qs.order_by().values(field).annotate(views=Sum('views')).order_by('-views', field)[:limit]
    return [{label: row[field], 'views': row['views']} for row in rows]


class StatsView(APIView):
    """GET manage/stats/?days=30 (1-365). Counts over the window except the
    current-state counts (unread enquiries, post, testimonial and gallery
    states) and posts.by_month (the last 12 calendar months). Each
    `previous` block is the same-length window just before this one. Day,
    month, status, realm and category series are zero-filled."""

    authentication_classes = [DashboardSessionAuthentication]
    permission_classes = [IsAdmin]

    def get(self, request):
        try:
            days = min(max(int(request.query_params.get('days', 30)), 1), 365)
        except ValueError:
            days = 30
        today = timezone.now().date()
        start_date = today - timedelta(days=days - 1)
        since = timezone.make_aware(datetime.combine(start_date, time.min), dt_timezone.utc)

        # The window before this one, the same length, for the trend notes.
        prev_start = start_date - timedelta(days=days)
        prev_since = timezone.make_aware(datetime.combine(prev_start, time.min), dt_timezone.utc)

        logins = LoginEvent.objects.filter(created__gte=since)
        prev_logins = LoginEvent.objects.filter(created__gte=prev_since, created__lt=since)
        login_days = logins.order_by().annotate(day=TruncDate('created')).values('day').annotate(
            n_success=Count('pk', filter=Q(success=True)), n_failed=Count('pk', filter=Q(success=False)),
        )
        login_days = [{'day': r['day'], 'success': r['n_success'], 'failed': r['n_failed']} for r in login_days]
        realm_rows = {
            r['realm']: r for r in logins.order_by().values('realm').annotate(
                n_success=Count('pk', filter=Q(success=True)), n_failed=Count('pk', filter=Q(success=False)),
            )
        }
        by_realm = [
            {'realm': realm, 'success': realm_rows.get(realm, {}).get('n_success', 0),
             'failed': realm_rows.get(realm, {}).get('n_failed', 0)}
            for realm in Realm.values
        ]

        enquiries = Enquiry.objects.filter(created__gte=since)
        by_source = [
            {'source': row['source'] or None, 'count': row['count']}
            for row in enquiries.order_by().values('source').annotate(count=Count('pk')).order_by('-count', 'source')
        ]
        enquiry_days = enquiries.order_by().annotate(day=TruncDate('created')).values('day').annotate(count=Count('pk'))
        by_status = _keyed(
            Enquiry.State.values, enquiries.order_by().values('status').annotate(count=Count('pk')), 'status'
        )

        revised = PostRevision.objects.filter(status=PostStatus.PENDING_REVIEW).count()
        post_status = _keyed(
            PostStatus.values, Post.objects.order_by().values('status').annotate(count=Count('pk')), 'status'
        )
        months = _months(today)
        month_since = timezone.make_aware(datetime.combine(months[0], time.min), dt_timezone.utc)
        month_rows = {
            r['month'].strftime('%Y-%m'): r['count']
            for r in Post.objects.filter(status=PostStatus.PUBLISHED, published_at__gte=month_since)
            .order_by().annotate(month=TruncMonth('published_at', tzinfo=dt_timezone.utc))
            .values('month').annotate(count=Count('pk'))
        }
        by_month = [{'month': m.strftime('%Y-%m'), 'count': month_rows.get(m.strftime('%Y-%m'), 0)} for m in months]

        visits = DailyVisit.objects.filter(date__gte=start_date)
        prev_visits = DailyVisit.objects.filter(date__gte=prev_start, date__lt=start_date)
        visit_days = visits.order_by().values(day=F('date')).annotate(views=Sum('views'))
        device_days = visits.order_by().values(day=F('date')).annotate(
            **{d: Sum('views', filter=Q(device=d)) for d in Device.values}
        )

        gallery = _keyed(
            GalleryCategory.values,
            GalleryItem.objects.order_by().values('category').annotate(count=Count('pk')),
            'category',
        )
        uncategorised = GalleryItem.objects.filter(category='').count()
        if uncategorised:
            gallery.append({'category': '', 'count': uncategorised})

        return Response({
            'days': days,
            'logins': {
                'success': logins.filter(success=True).count(),
                'failed': logins.filter(success=False).count(),
                'by_day': _series(start_date, days, login_days, ['success', 'failed']),
                'by_realm': by_realm,
                'previous': {
                    'success': prev_logins.filter(success=True).count(),
                    'failed': prev_logins.filter(success=False).count(),
                },
            },
            'enquiries': {
                'total': enquiries.count(),
                'unread': Enquiry.objects.filter(status=Enquiry.State.UNREAD).count(),
                'by_source': by_source,
                'by_day': _series(start_date, days, enquiry_days, ['count']),
                'by_status': by_status,
                'previous': {'total': Enquiry.objects.filter(created__gte=prev_since, created__lt=since).count()},
            },
            'posts': {
                'published': Post.objects.filter(status=PostStatus.PUBLISHED).count(),
                'pending_review': Post.objects.filter(status=PostStatus.PENDING_REVIEW).count() + revised,
                'drafts': Post.objects.filter(status__in=[PostStatus.DRAFT, PostStatus.CHANGES_REQUESTED]).count(),
                'changes_requested': Post.objects.filter(status=PostStatus.CHANGES_REQUESTED).count(),
                'edits_pending_review': revised,
                'by_status': post_status,
                'by_month': by_month,
            },
            'testimonials': {
                'pending': Testimonial.objects.filter(status=Testimonial.State.PENDING).count(),
                'published': Testimonial.objects.filter(status=Testimonial.State.PUBLISHED).count(),
                'rejected': Testimonial.objects.filter(status=Testimonial.State.REJECTED).count(),
            },
            'gallery': {
                'total': GalleryItem.objects.count(),
                'by_category': gallery,
            },
            'visits': {
                'total': visits.aggregate(n=Sum('views'))['n'] or 0,
                'by_day': _series(start_date, days, visit_days, ['views']),
                'by_day_device': _series(start_date, days, device_days, Device.values),
                'previous': {'total': prev_visits.aggregate(n=Sum('views'))['n'] or 0},
                'top_pages': _top(visits, 'path', 'path'),
                'countries': _top(visits.exclude(country=''), 'country', 'country'),
                'referrers': _top(visits.exclude(referrer_host=''), 'referrer_host', 'host'),
                'devices': _top(visits, 'device', 'device'),
            },
        })
