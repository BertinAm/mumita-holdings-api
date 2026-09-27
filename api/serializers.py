"""Read-only serializers. Translated fields are read through the model
attribute, which modeltranslation resolves to the active locale with
fallback to English."""

from rest_framework import serializers

from brands.models import Brand
from catalog.models import Product, Service
from content.models import GalleryItem, Post
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


class AuthorSerializer(serializers.ModelSerializer):
    """Byline, built the no-faces way (Review §8): name, department, qualification."""

    class Meta:
        model = TeamMember
        fields = ['slug', 'name', 'department', 'qualification']


class PostListSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = ['slug', 'title', 'dek', 'lens', 'author', 'published_at', 'media_key']

    def get_author(self, obj):
        a = obj.author
        # Only a published, consenting profile may be named.
        if a and a.status == 'published' and a.consent_to_publish:
            return AuthorSerializer(a).data
        return None


class PostDetailSerializer(PostListSerializer):
    class Meta(PostListSerializer.Meta):
        fields = PostListSerializer.Meta.fields + ['body', 'seo_title', 'meta_description']


class PartnerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Partner
        fields = ['slug', 'name', 'tier', 'logo', 'url', 'relationship', 'since_year']


class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Region
        fields = ['key', 'name', 'note', 'geo_key']


class GalleryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = GalleryItem
        fields = ['id', 'media_key', 'alt', 'caption', 'category', 'place', 'date', 'has_identifiable_faces']
