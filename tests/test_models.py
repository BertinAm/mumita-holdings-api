from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.test import TestCase
from django.utils import timezone

from brands.models import Brand
from catalog.models import Product
from common.models import Status
from content.models import Post
from engagement.models import Enquiry
from people.models import TeamMember


class ModelTests(TestCase):
    def test_team_member_has_no_photo_field(self):
        """Review §7: no individual face photographs, so no image/file field at all."""
        for field in TeamMember._meta.get_fields():
            self.assertNotIsInstance(field, (models.ImageField, models.FileField), field.name)
            self.assertNotIn('photo', field.name)
            self.assertNotIn('image', field.name)

    def test_product_has_no_price_field(self):
        names = [f.name for f in Product._meta.get_fields()]
        self.assertFalse([n for n in names if 'price' in n])

    def test_brand_line_parent_and_default_signoff(self):
        foods = Brand.objects.create(key='foods', slug='foods', name='Mumita Foods')
        lyda = Brand.objects.create(key='lyda', slug='lyda', name='LYDA', kind=Brand.Kind.LINE, parent=foods)
        self.assertEqual(list(foods.lines.all()), [lyda])
        self.assertEqual(foods.signoff, 'A Mumita Company')

    def test_translated_columns_exist_for_six_locales(self):
        for code in ('en', 'fr', 'sw', 'es', 'zh', 'pt'):
            Post._meta.get_field(f'title_{code}')
            Product._meta.get_field(f'name_{code}')

    def test_published_post_requires_original_date(self):
        post = Post(slug='a', title='A', body='b', status=Status.PUBLISHED)
        with self.assertRaises(ValidationError):
            post.clean()

    def test_published_manager_hides_drafts_and_future_posts(self):
        now = timezone.now()
        Post.objects.create(slug='live', title='Live', body='x', status=Status.PUBLISHED, published_at=now - timedelta(days=1))
        Post.objects.create(slug='draft', title='Draft', body='x', status=Status.DRAFT, published_at=now)
        Post.objects.create(slug='later', title='Later', body='x', status=Status.PUBLISHED, published_at=now + timedelta(days=1))
        self.assertEqual([p.slug for p in Post.objects.published()], ['live'])

    def test_enquiry_gets_retention_date(self):
        e = Enquiry.objects.create(name='A B', contact='a@example.com', contact_kind='email', enquiry_type='buy', message='hi')
        self.assertGreater(e.retention_until, timezone.now().date())
