from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import LoginEvent
from analytics.models import DailyVisit
from content.models import Post, PostRevision
from engagement.models import Enquiry, Testimonial

from .helpers import DashboardTestCase

HIT = '/api/v1/analytics/hit/'
KEY = 'test-analytics-key'


@override_settings(ANALYTICS_INGEST_KEY=KEY)
class HitTests(TestCase):
    def hit(self, key=KEY, **data):
        body = {'path': '/products', 'referrer_host': 'www.google.com', 'country': 'cm', 'device': 'mobile',
                'is_bot': False}
        body.update(data)
        headers = {'HTTP_X_ANALYTICS_KEY': key} if key is not None else {}
        return APIClient().post(HIT, body, format='json', **headers)

    def test_key_required(self):
        self.assertEqual(self.hit(key=None).status_code, 403)
        self.assertEqual(self.hit(key='wrong').status_code, 403)
        self.assertFalse(DailyVisit.objects.exists())

    @override_settings(ANALYTICS_INGEST_KEY='')
    def test_disabled_without_configured_key(self):
        self.assertEqual(self.hit(key='').status_code, 403)

    def test_hits_aggregate_per_day_path_country_referrer_device(self):
        self.assertEqual(self.hit().status_code, 204)
        self.assertEqual(self.hit(path='/products/?utm=x#top').status_code, 204)
        self.hit(device='desktop')
        rows = list(DailyVisit.objects.order_by('device').values_list('path', 'country', 'referrer_host', 'device', 'views'))
        self.assertEqual(rows, [('/products', 'CM', 'google.com', 'desktop', 1), ('/products', 'CM', 'google.com', 'mobile', 2)])
        self.assertEqual(DailyVisit.objects.first().date, timezone.now().date())

    def test_bots_dropped(self):
        self.assertEqual(self.hit(is_bot=True).status_code, 204)
        self.assertFalse(DailyVisit.objects.exists())

    def test_validation(self):
        self.assertEqual(self.hit(device='fridge').status_code, 400)
        self.assertEqual(self.hit(path='products').status_code, 400)
        self.hit(country='XX', referrer_host='not a host!')
        row = DailyVisit.objects.get()
        self.assertEqual((row.country, row.referrer_host), ('', ''))


class StatsTests(DashboardTestCase):
    def test_admin_only(self):
        self.assertEqual(self.client_for(None).get('/api/v1/manage/stats/').status_code, 401)
        self.assertEqual(self.client_for(self.pub).get('/api/v1/manage/stats/').status_code, 403)

    def test_shape_and_counts(self):
        today = timezone.now().date()
        LoginEvent.objects.create(realm='admin', username='a', success=True, outcome='success')
        LoginEvent.objects.create(realm='admin', username='a', success=False, outcome='bad_credentials')
        Enquiry.objects.create(name='A', contact='a@example.com', contact_kind='email', enquiry_type='buy',
                               message='m', source='contact')
        Enquiry.objects.create(name='B', contact='b@example.com', contact_kind='email', enquiry_type='buy',
                               message='m', status='read')
        live = Post.objects.create(slug='a', title='A', status='published', published_at=timezone.now())
        PostRevision.objects.create(post=live, slug='a', title='A2')
        Post.objects.create(slug='b', title='B', status='pending_review')
        Post.objects.create(slug='c', title='C', status='draft')
        Testimonial.objects.create(name='T', quote='q', consent=True)
        DailyVisit.objects.create(date=today, path='/', country='CM', referrer_host='google.com', device='mobile', views=5)
        DailyVisit.objects.create(date=today - timedelta(days=1), path='/blog', country='FR', device='desktop', views=2)
        DailyVisit.objects.create(date=today - timedelta(days=60), path='/old', device='desktop', views=100)

        s = self.client_for(self.admin).get('/api/v1/manage/stats/?days=30').json()
        self.assertEqual(set(s), {'days', 'logins', 'enquiries', 'posts', 'testimonials', 'visits'})
        self.assertEqual((s['logins']['success'], s['logins']['failed']), (1, 1))
        self.assertEqual(len(s['logins']['by_day']), 30)
        self.assertEqual(s['logins']['by_day'][-1], {'date': today.isoformat(), 'success': 1, 'failed': 1})
        self.assertEqual((s['enquiries']['total'], s['enquiries']['unread']), (2, 1))
        self.assertEqual({r['source'] for r in s['enquiries']['by_source']}, {'contact', None})
        self.assertEqual(s['posts'], {'published': 1, 'pending_review': 2, 'drafts': 1})
        self.assertEqual(s['testimonials'], {'pending': 1, 'published': 0})
        v = s['visits']
        self.assertEqual(v['total'], 7)
        self.assertEqual(v['by_day'][-1], {'date': today.isoformat(), 'views': 5})
        self.assertEqual(v['top_pages'], [{'path': '/', 'views': 5}, {'path': '/blog', 'views': 2}])
        self.assertEqual(v['countries'][0], {'country': 'CM', 'views': 5})
        self.assertEqual(v['referrers'], [{'host': 'google.com', 'views': 5}])
        self.assertEqual({d['device'] for d in v['devices']}, {'mobile', 'desktop'})

    def test_days_clamped(self):
        s = self.client_for(self.admin).get('/api/v1/manage/stats/?days=9999').json()
        self.assertEqual(s['days'], 365)
