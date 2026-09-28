from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from brands.models import Brand
from catalog.models import Product
from common.models import Status
from content.models import Post
from people.models import Partner, TeamMember

P = Status.PUBLISHED


class ApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.foods = Brand.objects.create(key='foods', slug='foods', name='Mumita Foods', status=P)
        self.prais = Brand.objects.create(key='prais', slug='prais', name='Praïs', status=P)
        hidden = Brand.objects.create(key='agro', slug='agro', name='Agro', status=Status.DRAFT)
        Product.objects.create(brand=self.foods, slug='flour', name_en='Flour', status=P)
        Product.objects.create(brand=self.foods, slug='draft', name_en='Draft', status=Status.DRAFT)
        Product.objects.create(brand=self.prais, slug='meal', name_en='Meal', status=P)
        Product.objects.create(brand=hidden, slug='orphan', name_en='Orphan', status=P)

    def slugs(self, url):
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200, res.content)
        return [row.get('slug') or row.get('key') for row in res.json()['results']]

    def test_products_published_only(self):
        self.assertEqual(sorted(self.slugs('/api/v1/products/')), ['flour', 'meal'])

    def test_products_filter_by_brand(self):
        self.assertEqual(self.slugs('/api/v1/products/?brand=foods'), ['flour'])

    def test_draft_detail_is_404(self):
        self.assertEqual(self.client.get('/api/v1/products/draft/').status_code, 404)

    def test_brands_published_only(self):
        self.assertEqual(sorted(self.slugs('/api/v1/brands/')), ['foods', 'prais'])

    def test_posts_published_only_and_no_future(self):
        now = timezone.now()
        Post.objects.create(slug='live', title_en='Live', body_en='x', status=P, published_at=now - timedelta(days=2))
        Post.objects.create(slug='draft', title_en='Draft', body_en='x', status=Status.REVIEW, published_at=now)
        Post.objects.create(slug='soon', title_en='Soon', body_en='x', status=P, published_at=now + timedelta(days=2))
        self.assertEqual(self.slugs('/api/v1/posts/'), ['live'])
        self.assertIn('body_html', self.client.get('/api/v1/posts/live/').json())

    def test_team_requires_consent(self):
        TeamMember.objects.create(name='A', slug='a', department='it', status=P, consent_to_publish=True)
        TeamMember.objects.create(name='B', slug='b', department='it', status=P, consent_to_publish=False)
        self.assertEqual(self.slugs('/api/v1/team/'), ['a'])

    def test_author_without_consent_is_not_named(self):
        b = TeamMember.objects.create(name='B', slug='b', department='hr', status=P, consent_to_publish=False)
        Post.objects.create(slug='p', title_en='P', body_en='x', status=P, published_at=timezone.now(), author=b)
        # The byline falls back to the organisation, never the unconsented name.
        self.assertEqual(self.client.get('/api/v1/posts/p/').json()['author'], 'Mumita Holdings')

    def test_partners_require_permission_and_filter_by_tier(self):
        Partner.objects.create(name='C', slug='c', tier='buyer', status=P, permission_to_display=True)
        Partner.objects.create(name='U', slug='u', tier='institutional', status=P, permission_to_display=True)
        Partner.objects.create(name='X', slug='x', tier='buyer', status=P, permission_to_display=False)
        self.assertEqual(self.slugs('/api/v1/partners/?tier=buyer'), ['c'])

    def test_pagination_envelope(self):
        body = self.client.get('/api/v1/products/').json()
        self.assertEqual(set(body), {'count', 'next', 'previous', 'results'})

    def test_read_only(self):
        self.assertEqual(self.client.post('/api/v1/products/', {}, format='json').status_code, 405)


class LocaleTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        foods = Brand.objects.create(key='foods', slug='foods', name='Mumita Foods', status=P)
        Product.objects.create(
            brand=foods, slug='flour', name_en='Plantain Flour', name_fr='Farine de plantain',
            blurb_en='English blurb', status=P,
        )

    def get(self, url, **headers):
        return self.client.get(url, **headers)

    def test_lang_query_param(self):
        res = self.get('/api/v1/products/flour/?lang=fr')
        self.assertEqual(res.json()['name'], 'Farine de plantain')
        self.assertEqual(res['Content-Language'], 'fr')

    def test_accept_language_header(self):
        res = self.get('/api/v1/products/flour/', HTTP_ACCEPT_LANGUAGE='fr-FR,fr;q=0.9,en;q=0.8')
        self.assertEqual(res.json()['name'], 'Farine de plantain')
        self.assertIn('Accept-Language', res['Vary'])

    def test_missing_translation_falls_back_to_english(self):
        res = self.get('/api/v1/products/flour/?lang=fr')
        self.assertEqual(res.json()['blurb'], 'English blurb')
        res = self.get('/api/v1/products/flour/?lang=sw')
        self.assertEqual(res.json()['name'], 'Plantain Flour')

    def test_unknown_locale_is_english(self):
        res = self.get('/api/v1/products/flour/?lang=de')
        self.assertEqual(res['Content-Language'], 'en')
        self.assertEqual(res.json()['name'], 'Plantain Flour')

    def test_zh_hans_maps_to_zh(self):
        Product.objects.filter(slug='flour').update(name_zh='大蕉粉')
        res = self.get('/api/v1/products/flour/', HTTP_ACCEPT_LANGUAGE='zh-Hans-CN')
        self.assertEqual(res.json()['name'], '大蕉粉')
