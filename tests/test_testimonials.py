from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from engagement.models import Testimonial

from .helpers import REVALIDATE_SETTINGS, DashboardTestCase

SUBMIT = '/api/v1/testimonials/submit/'
VALID = {'name': 'Grace N.', 'role_or_place': 'Cooperative member, Muea', 'quote': 'The training changed how we store our harvest.',
         'consent': True, 'website': ''}


@override_settings(CORS_ALLOWED_ORIGINS=['https://mumita.example'])
class TestimonialSubmitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def post(self, data, **headers):
        return self.client.post(SUBMIT, data, format='json', **headers)

    def test_submit_lands_pending_and_is_not_public(self):
        res = self.post(VALID)
        self.assertEqual(res.status_code, 201, res.content)
        t = Testimonial.objects.get()
        self.assertEqual((t.status, t.consent, len(t.ip_hash)), ('pending', True, 64))
        self.assertEqual(self.client.get('/api/v1/testimonials/').json()['count'], 0)

    def test_consent_required(self):
        for consent in (False, None, 'yes-ish'):
            cache.clear()
            res = self.post({**VALID, 'consent': consent})
            self.assertEqual(res.status_code, 400, consent)
            self.assertIn('consent', res.json())
        body = dict(VALID)
        del body['consent']
        cache.clear()
        self.assertEqual(self.post(body).status_code, 400)
        self.assertFalse(Testimonial.objects.exists())

    def test_honeypot(self):
        self.assertEqual(self.post({**VALID, 'website': 'http://spam.example'}).status_code, 201)
        self.assertFalse(Testimonial.objects.exists())

    def test_extra_fields_and_foreign_origin_refused(self):
        self.assertEqual(self.post({**VALID, 'photo': 'x'}).status_code, 400)
        self.assertEqual(self.post(VALID, HTTP_ORIGIN='https://evil.example').status_code, 403)

    def test_throttle(self):
        codes = [self.post(VALID).status_code for _ in range(4)]
        self.assertEqual(codes, [201, 201, 201, 429])


@override_settings(**REVALIDATE_SETTINGS)
@mock.patch('common.revalidate._post', return_value=200)
class TestimonialManageTests(DashboardTestCase):
    def setUp(self):
        super().setUp()
        self.m = self.client_for(self.admin)
        self.t = Testimonial.objects.create(name='Grace N.', quote='Good training.', consent=True)

    def test_approve_publishes_and_revalidates(self, _post):
        with self.captureOnCommitCallbacks(execute=True):
            res = self.m.post(f'/api/v1/manage/testimonials/{self.t.pk}/approve/')
        self.assertEqual(res.json()['status'], 'published')
        public = self.client_for(None).get('/api/v1/testimonials/').json()['results']
        self.assertEqual(public, [{'id': self.t.pk, 'name': 'Grace N.', 'role_or_place': '', 'quote': 'Good training.',
                                   'photo': None}])
        self.assertEqual(_post.call_args.args[0], ['/'])

    def test_reject_and_delete(self, _post):
        res = self.m.post(f'/api/v1/manage/testimonials/{self.t.pk}/reject/')
        self.assertEqual(res.json()['status'], 'rejected')
        self.assertEqual(self.m.delete(f'/api/v1/manage/testimonials/{self.t.pk}/').status_code, 204)

    def test_cannot_publish_without_consent(self, _post):
        t = Testimonial.objects.create(name='No Consent', quote='Hmm.', consent=False)
        self.assertEqual(self.m.post(f'/api/v1/manage/testimonials/{t.pk}/approve/').status_code, 400)
        res = self.m.post('/api/v1/manage/testimonials/', {'name': 'X Y', 'quote': 'Great.', 'status': 'published'},
                          format='json')
        self.assertEqual(res.status_code, 400)
        res = self.m.post('/api/v1/manage/testimonials/', {'name': 'X Y', 'quote': 'Great.', 'consent': True,
                                                            'status': 'published'}, format='json')
        self.assertEqual(res.status_code, 201)

    def test_list_filter_and_patch(self, _post):
        self.assertEqual(self.m.get('/api/v1/manage/testimonials/?status=pending').json()['count'], 1)
        res = self.m.patch(f'/api/v1/manage/testimonials/{self.t.pk}/', {'quote': 'Very good training.'}, format='json')
        self.assertEqual(res.json()['quote'], 'Very good training.')

    def test_publishers_refused(self, _post):
        self.assertEqual(self.client_for(self.pub).get('/api/v1/manage/testimonials/').status_code, 403)
