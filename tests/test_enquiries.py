from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from engagement.models import Enquiry

URL = '/api/v1/enquiries/'
VALID = {'name': 'Ada Buyer', 'contact': 'ada@example.com', 'type': 'buy', 'message': 'Ten cartons of flour, please.'}


@override_settings(ENQUIRY_NOTIFY_EMAILS=['staff@example.com'], CORS_ALLOWED_ORIGINS=['https://mumita.example'])
class EnquiryTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def post(self, data, **headers):
        return self.client.post(URL, data, format='json', **headers)

    def test_valid_enquiry_is_stored_and_emailed(self):
        res = self.post(VALID, HTTP_ACCEPT_LANGUAGE='fr', HTTP_REFERER='https://mumita.example/fr/contact')
        self.assertEqual(res.status_code, 201, res.content)
        e = Enquiry.objects.get()
        self.assertEqual((e.name, e.contact_kind, e.enquiry_type, e.locale), ('Ada Buyer', 'email', 'buy', 'fr'))
        self.assertEqual(e.page, 'https://mumita.example/fr/contact')
        self.assertTrue(e.staff_notified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['staff@example.com'])
        self.assertIn('Ten cartons', mail.outbox[0].body)
        self.assertNotIn('Ada', mail.outbox[0].subject)
        self.assertEqual(len(e.ip_hash), 64)

    def test_phone_contact(self):
        res = self.post({**VALID, 'contact': '+237 650 754 393'})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Enquiry.objects.get().contact_kind, 'phone')

    def test_fifth_field_rejected(self):
        res = self.post({**VALID, 'location': 'Buea'})
        self.assertEqual(res.status_code, 400)
        self.assertIn('location', res.json())
        self.assertFalse(Enquiry.objects.exists())

    def test_missing_and_invalid_fields(self):
        res = self.post({'name': 'A'})
        self.assertEqual(res.status_code, 400)
        self.assertTrue({'name', 'contact', 'type', 'message'} <= set(res.json()))
        for bad in ({'contact': 'not-an-email@'}, {'contact': '12'}, {'type': 'sell'}, {'message': 'x' * 2001}):
            self.assertEqual(self.post({**VALID, **bad}).status_code, 400, bad)
        self.assertFalse(Enquiry.objects.exists())

    def test_control_characters_stripped(self):
        self.assertEqual(self.post({**VALID, 'name': 'Ada\x00 Buyer'}).status_code, 400)
        self.post({**VALID, 'name': 'Ada Buyer\x07\x1b', 'message': 'Line one\r\nLine two\x08'})
        e = Enquiry.objects.get()
        self.assertEqual((e.name, e.message), ('Ada Buyer', 'Line one\nLine two'))

    def test_honeypot_looks_like_success_but_stores_nothing(self):
        res = self.post({**VALID, 'website': 'http://spam.example'})
        self.assertEqual(res.status_code, 201)
        self.assertFalse(Enquiry.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_empty_honeypot_is_fine(self):
        self.assertEqual(self.post({**VALID, 'website': ''}).status_code, 201)

    def test_foreign_origin_refused(self):
        res = self.post(VALID, HTTP_ORIGIN='https://evil.example')
        self.assertEqual(res.status_code, 403)
        self.assertEqual(self.post(VALID, HTTP_ORIGIN='https://mumita.example').status_code, 201)

    def test_cors_header_only_for_allowed_origin(self):
        res = self.client.options(URL, HTTP_ORIGIN='https://mumita.example', HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST')
        self.assertEqual(res['access-control-allow-origin'], 'https://mumita.example')
        res = self.client.options(URL, HTTP_ORIGIN='https://evil.example', HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST')
        self.assertNotIn('access-control-allow-origin', res)

    def test_throttle(self):
        codes = [self.post(VALID).status_code for _ in range(6)]
        self.assertEqual(codes, [201] * 5 + [429])

    def test_message_body_not_logged(self):
        with self.assertLogs('engagement', level='INFO') as logs:
            self.post(VALID)
        joined = '\n'.join(logs.output)
        self.assertNotIn('Ten cartons', joined)
        self.assertNotIn('ada@example.com', joined)

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(URL).status_code, 405)
