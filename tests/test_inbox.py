from django.core import mail

from engagement.models import Enquiry, EnquiryReply

from .helpers import DashboardTestCase

M = '/api/v1/manage/enquiries/'


def enquiry(**kw):
    data = {'name': 'Ada Buyer', 'contact': 'ada@example.com', 'contact_kind': 'email', 'enquiry_type': 'buy',
            'message': 'Ten cartons of flour, please.', 'source': 'contact'}
    data.update(kw)
    return Enquiry.objects.create(**data)


class InboxTests(DashboardTestCase):
    def setUp(self):
        super().setUp()
        self.m = self.client_for(self.admin)

    def test_admin_only(self):
        self.assertEqual(self.client_for(None).get(M).status_code, 401)
        self.assertEqual(self.client_for(self.pub).get(M).status_code, 403)

    def test_list_filters_and_search(self):
        enquiry()
        enquiry(name='Ben Farmer', source='partners', message='Cold room rental', status='archived')
        enquiry(name='Cy', source='', topic='Plantain Flour')
        self.assertEqual(self.m.get(M).json()['count'], 3)
        self.assertEqual(self.m.get(M + '?source=partners').json()['count'], 1)
        self.assertEqual(self.m.get(M + '?source=none').json()['count'], 1)
        self.assertEqual(self.m.get(M + '?status=archived').json()['count'], 1)
        self.assertEqual(self.m.get(M + '?status=unread').json()['count'], 2)
        self.assertEqual(self.m.get(M + '?q=cold room').json()['count'], 1)
        self.assertEqual(self.m.get(M + '?q=plantain').json()['count'], 1)
        row = self.m.get(M + '?source=partners').json()['results'][0]
        self.assertEqual(row['type'], 'buy')
        self.assertEqual(row['reply_count'], 0)

    def test_open_marks_read_and_patch_status(self):
        e = enquiry()
        self.assertEqual(self.m.get(f'{M}{e.pk}/').json()['status'], 'read')
        res = self.m.patch(f'{M}{e.pk}/', {'status': 'archived'}, format='json')
        self.assertEqual(res.json()['status'], 'archived')
        self.assertEqual(self.m.patch(f'{M}{e.pk}/', {'status': 'deleted'}, format='json').status_code, 400)
        self.assertEqual(self.m.patch(f'{M}{e.pk}/', {'status': 'read', 'name': 'X'}, format='json').status_code, 400)
        self.assertEqual(self.m.delete(f'{M}{e.pk}/').status_code, 405)

    def test_reply_by_email(self):
        e = enquiry()
        res = self.m.post(f'{M}{e.pk}/reply/', {'message': 'We can deliver next week.'}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, ['ada@example.com'])
        self.assertEqual(msg.reply_to, [self.admin.email])
        self.assertIn('We can deliver next week.', msg.body)
        self.assertIn('Ten cartons', msg.body)
        e.refresh_from_db()
        self.assertEqual(e.status, 'replied')
        reply = EnquiryReply.objects.get()
        self.assertEqual((reply.author, reply.emailed), (self.admin, True))
        detail = self.m.get(f'{M}{e.pk}/').json()
        self.assertEqual(detail['replies'][0]['author']['name'], 'Admin One')

    def test_reply_to_phone_contact(self):
        e = enquiry(contact='+237 650 754 393', contact_kind='phone')
        res = self.m.post(f'{M}{e.pk}/reply/', {'message': 'Calling you.'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json(), {'detail': 'phone'})
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(EnquiryReply.objects.exists())

    def test_reply_needs_text(self):
        e = enquiry()
        self.assertEqual(self.m.post(f'{M}{e.pk}/reply/', {'message': ' '}, format='json').status_code, 400)
