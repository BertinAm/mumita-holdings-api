"""Read-only serializers. Translated fields are read through the model
attribute, which modeltranslation resolves to the active locale with
fallback to English."""

from rest_framework import serializers

from brands.models import Brand
from catalog.models import Product, Service
from content.images import image_payload
from content.models import GalleryItem, Post, auto_excerpt, reading_minutes
from people.models import Partner, Region, TeamMember


def lines(value):
    return [line.strip() for line in (value or '').splitlines() if line.strip()]


class BrandSerializer(serializers.ModelSerializer):
    parent = serializers.SlugRelatedField(slug_field='key', read_only=True)

    class Meta:
        model = Brand
        fields = [
            'key', 'slug', 'name', 'short_name', 'role', 'summary', 'step_body', 'signoff',
            'logo', 'palette_status', 'kind', 'parent', 'external_url',
        ]


class ProductSerializer(serializers.ModelSerializer):
    brand = serializers.SlugRelatedField(slug_field='key', read_only=True)

    class Meta:
        model = Product
        # No price: none is published (SITEMAP §5).
        fields = [
            'slug', 'brand', 'name', 'category', 'blurb', 'description', 'ingredients', 'uses',
            'shelf_life', 'weight', 'media_key', 'cutout', 'alt', 'is_on_sale',
        ]


class ServiceSerializer(serializers.ModelSerializer):
    brand = serializers.SlugRelatedField(slug_field='key', read_only=True)
    includes = serializers.SerializerMethodField()
    process_steps = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = ['slug', 'brand', 'name', 'summary', 'includes', 'process_steps', 'price_note', 'media_key']

    def get_includes(self, obj):
        return lines(obj.includes)

    def get_process_steps(self, obj):
        return lines(obj.process_steps)


class TeamMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeamMember
        fields = ['slug', 'name', 'qualification', 'years_experience', 'department', 'tier', 'value_statement']


class PostListSerializer(serializers.ModelSerializer):
    """PLATFORM-CONTRACT "Public": author is a display name; cover is an
    image object (null for migrated posts, which carry `media_key`)."""

    author = serializers.CharField(source='author_name', read_only=True)
    excerpt = serializers.SerializerMethodField()
    reading_minutes = serializers.SerializerMethodField()
    cover = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            'slug', 'title', 'dek', 'excerpt', 'lens', 'author', 'published_at', 'reading_minutes',
            'cover', 'media_key',
        ]

    def get_excerpt(self, obj):
        return obj.excerpt or auto_excerpt(obj.body)

    def get_reading_minutes(self, obj):
        return reading_minutes(obj.body)

    def get_cover(self, obj):
        return image_payload(obj.cover, self.context.get('request'))


class PostDetailSerializer(PostListSerializer):
    body_html = serializers.CharField(source='body', read_only=True)

    class Meta(PostListSerializer.Meta):
        fields = PostListSerializer.Meta.fields + ['body_html', 'seo_title', 'seo_description']


class PartnerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Partner
        fields = ['slug', 'name', 'tier', 'logo', 'url', 'relationship', 'since_year']


class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Region
        fields = ['key', 'name', 'note', 'geo_key']


class GalleryItemSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = GalleryItem
        fields = ['id', 'category', 'alt', 'caption', 'image']

    def get_image(self, obj):
        return image_payload(obj.image, self.context.get('request'))
