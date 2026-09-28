from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import LoginEvent
from common.security import client_ip, hash_ip

rf = RequestFactory()


def req(remote='203.0.113.9', **headers):
    return rf.get('/', REMOTE_ADDR=remote, **headers)


class ClientIpTests(SimpleTestCase):
    def test_default_ignores_forwarded_for(self):
        self.assertEqual(client_ip(req(HTTP_X_FORWARDED_FOR='198.51.100.1')), '203.0.113.9')

    @override_settings(NUM_PROXIES=1)
    def test_num_proxies_takes_the_hop_our_proxy_appended(self):
        r = req('127.0.0.1', HTTP_X_FORWARDED_FOR='6.6.6.6, 198.51.100.1')
        self.assertEqual(client_ip(r), '198.51.100.1')

    @override_settings(TRUSTED_PROXY_KEY='test-proxy-key')
    def test_key_marks_the_worker_and_first_hop_is_used(self):
        worker = req(HTTP_X_FORWARDED_FOR='198.51.100.7, 172.70.1.1', HTTP_X_PROXY_KEY='test-proxy-key')
        self.assertEqual(client_ip(worker), '198.51.100.7')
        forged = req(HTTP_X_FORWARDED_FOR='198.51.100.7', HTTP_X_PROXY_KEY='guess')
        self.assertEqual(client_ip(forged), '203.0.113.9')

    @override_settings(TRUSTED_PROXIES=['172.64.0.0/13'])
    def test_trusted_networks(self):
        self.assertEqual(client_ip(req('172.70.1.1', HTTP_X_FORWARDED_FOR='198.51.100.7')), '198.51.100.7')
        self.assertEqual(client_ip(req('203.0.113.50', HTTP_X_FORWARDED_FOR='198.51.100.7')), '203.0.113.50')

    @override_settings(TRUSTED_PROXY_KEY='test-proxy-key', TRUSTED_PROXY_HEADER='CF-Connecting-IP')
    def test_custom_header_and_garbage(self):
        r = req(HTTP_CF_CONNECTING_IP='2001:db8::1', HTTP_X_PROXY_KEY='test-proxy-key')
        self.assertEqual(client_ip(r), '2001:db8::1')
        r = req(HTTP_CF_CONNECTING_IP='not-an-ip', HTTP_X_PROXY_KEY='test-proxy-key')
        self.assertEqual(client_ip(r), '203.0.113.9')


class ForwardedIpIntegrationTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_spoofed_forwarded_for_does_not_dodge_the_throttle(self):
        client = APIClient()
        body = {'name': 'Ada Buyer', 'contact': 'ada@example.com', 'type': 'buy', 'message': 'Hello there.'}
        codes = [client.post('/api/v1/enquiries/', body, format='json', HTTP_X_FORWARDED_FOR=f'10.0.0.{i}').status_code
                 for i in range(6)]
        self.assertEqual(codes[-1], 429)

    @override_settings(TRUSTED_PROXY_KEY='test-proxy-key')
    def test_login_event_hashes_forwarded_visitor_ip(self):
        APIClient().post('/api/v1/auth/login/', {'email': 'test-x@mumitaholdings.com', 'password': 'y', 'realm': 'admin'},
                         format='json', HTTP_X_FORWARDED_FOR='198.51.100.7', HTTP_X_PROXY_KEY='test-proxy-key')
        self.assertEqual(LoginEvent.objects.get().ip_hash, hash_ip('198.51.100.7'))
