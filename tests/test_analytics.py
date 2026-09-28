from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import LoginEvent
from analytics.models import DailyVisit
from content.models import GalleryItem, Post, PostRevision
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
        self.assertEqual(set(s), {'days', 'logins', 'enquiries', 'posts', 'testimonials', 'visits', 'gallery'})
        self.assertEqual((s['logins']['success'], s['logins']['failed']), (1, 1))
        self.assertEqual(len(s['logins']['by_day']), 30)
        self.assertEqual(s['logins']['by_day'][-1], {'date': today.isoformat(), 'success': 1, 'failed': 1})
        self.assertEqual((s['enquiries']['total'], s['enquiries']['unread']), (2, 1))
        self.assertEqual({r['source'] for r in s['enquiries']['by_source']}, {'contact', None})
        posts = {k: s['posts'][k] for k in ('published', 'pending_review', 'drafts')}
        self.assertEqual(posts, {'published': 1, 'pending_review': 2, 'drafts': 1})
        self.assertEqual((s['testimonials']['pending'], s['testimonials']['published']), (1, 0))
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


class StatsSeriesTests(DashboardTestCase):
    """The chart series added for the Overview charts (additive keys)."""

    def stats(self, days=7):
        return self.client_for(self.admin).get(f'/api/v1/manage/stats/?days={days}').json()

    def test_empty_install_is_zero_filled(self):
        s = self.stats(7)
        self.assertEqual(len(s['enquiries']['by_day']), 7)
        self.assertTrue(all(d['count'] == 0 for d in s['enquiries']['by_day']))
        self.assertEqual([r['status'] for r in s['enquiries']['by_status']], ['unread', 'read', 'replied', 'archived'])
        self.assertEqual(s['enquiries']['previous'], {'total': 0})
        self.assertEqual(s['logins']['by_realm'], [
            {'realm': 'admin', 'success': 0, 'failed': 0}, {'realm': 'publisher', 'success': 0, 'failed': 0},
        ])
        self.assertEqual(s['logins']['previous'], {'success': 0, 'failed': 0})
        self.assertEqual(len(s['posts']['by_month']), 12)
        self.assertEqual(s['posts']['by_month'][-1]['month'], timezone.now().strftime('%Y-%m'))
        self.assertEqual([r['status'] for r in s['posts']['by_status']],
                         ['draft', 'pending_review', 'changes_requested', 'published'])
        self.assertEqual(s['visits']['by_day_device'][-1],
                         {'date': timezone.now().date().isoformat(), 'mobile': 0, 'tablet': 0, 'desktop': 0})
        self.assertEqual(s['visits']['previous'], {'total': 0})
        self.assertEqual(s['gallery']['total'], 0)
        self.assertEqual(len(s['gallery']['by_category']), 10)
        self.assertTrue(all(r['count'] == 0 for r in s['gallery']['by_category']))

    def test_series_and_previous_window(self):
        now = timezone.now()
        today = now.date()
        e1 = Enquiry.objects.create(name='A', contact='a@example.com', contact_kind='email', enquiry_type='buy',
                                    message='m', status='replied')
        Enquiry.objects.create(name='B', contact='b@example.com', contact_kind='email', enquiry_type='buy', message='m')
        old = Enquiry.objects.create(name='C', contact='c@example.com', contact_kind='email', enquiry_type='buy',
                                     message='m')
        # created is auto_now_add: move rows with update().
        Enquiry.objects.filter(pk=e1.pk).update(created=now - timedelta(days=2))
        Enquiry.objects.filter(pk=old.pk).update(created=now - timedelta(days=9))  # previous 7-day window
        LoginEvent.objects.create(realm='publisher', username='p', success=False, outcome='bad_credentials')
        LoginEvent.objects.create(realm='admin', username='a', success=True, outcome='success')
        prev_login = LoginEvent.objects.create(realm='admin', username='a', success=True, outcome='success')
        LoginEvent.objects.filter(pk=prev_login.pk).update(created=now - timedelta(days=10))
        Post.objects.create(slug='p1', title='P1', status='published', published_at=now)
        Post.objects.create(slug='p2', title='P2', status='published', published_at=now - timedelta(days=400))
        Post.objects.create(slug='p3', title='P3', status='changes_requested')
        DailyVisit.objects.create(date=today, path='/', device='mobile', views=4)
        DailyVisit.objects.create(date=today, path='/', device='desktop', views=3)
        DailyVisit.objects.create(date=today - timedelta(days=1), path='/', device='tablet', views=2)
        DailyVisit.objects.create(date=today - timedelta(days=8), path='/', device='desktop', views=11)
        GalleryItem.objects.create(alt='a', category='farms')
        GalleryItem.objects.create(alt='b', category='farms')
        GalleryItem.objects.create(alt='c')

        s = self.stats(7)
        e = s['enquiries']
        self.assertEqual(e['total'], 2)
        self.assertEqual(sum(d['count'] for d in e['by_day']), 2)
        self.assertEqual(e['by_day'][-3], {'date': (today - timedelta(days=2)).isoformat(), 'count': 1})
        self.assertEqual({r['status']: r['count'] for r in e['by_status']},
                         {'unread': 1, 'read': 0, 'replied': 1, 'archived': 0})
        self.assertEqual(e['previous'], {'total': 1})

        lg = s['logins']
        self.assertEqual(lg['by_realm'], [
            {'realm': 'admin', 'success': 1, 'failed': 0}, {'realm': 'publisher', 'success': 0, 'failed': 1},
        ])
        self.assertEqual(lg['previous'], {'success': 1, 'failed': 0})

        p = s['posts']
        self.assertEqual(p['changes_requested'], 1)
        self.assertEqual(p['edits_pending_review'], 0)
        self.assertEqual({r['status']: r['count'] for r in p['by_status']},
                         {'draft': 0, 'pending_review': 0, 'changes_requested': 1, 'published': 2})
        self.assertEqual(p['by_month'][-1], {'month': now.strftime('%Y-%m'), 'count': 1})
        self.assertEqual(sum(m['count'] for m in p['by_month']), 1)  # the 400-day-old post is outside

        v = s['visits']
        self.assertEqual(v['by_day_device'][-1]['mobile'], 4)
        self.assertEqual(v['by_day_device'][-1]['desktop'], 3)
        self.assertEqual(v['by_day_device'][-2]['tablet'], 2)
        self.assertEqual(sum(d['mobile'] + d['desktop'] + d['tablet'] for d in v['by_day_device']), v['total'])
        self.assertEqual(v['previous'], {'total': 11})

        g = s['gallery']
        self.assertEqual(g['total'], 3)
        counts = {r['category']: r['count'] for r in g['by_category']}
        self.assertEqual((counts['farms'], counts['prais'], counts['']), (2, 0, 1))
