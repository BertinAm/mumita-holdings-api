from django.utils.cache import patch_cache_control
from rest_framework import viewsets

from brands.models import Brand
from catalog.models import Product, Service
from content.models import GalleryItem, Post
from people.models import Partner, Region, TeamMember

from . import serializers as s


class PublicReadOnlyViewSet(viewsets.ReadOnlyModelViewSet):
    """Published rows only. `filters` maps a query parameter to an ORM lookup;
    unknown parameters are ignored."""

    authentication_classes = []
    lookup_field = 'slug'
    filters = {}

    def base_queryset(self):
        return self.queryset.model.objects.published()

    def get_queryset(self):
        qs = self.base_queryset()
        for param, lookup in self.filters.items():
            value = self.request.query_params.get(param)
            if value:
                qs = qs.filter(**{lookup: value})
        return qs

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        if request.method == 'GET' and response.status_code == 200:
            patch_cache_control(response, public=True, max_age=300)
        return response


class BrandViewSet(PublicReadOnlyViewSet):
    queryset = Brand.objects.none()
    serializer_class = s.BrandSerializer
    filters = {'kind': 'kind', 'parent': 'parent__key'}

    def base_queryset(self):
        return Brand.objects.published().select_related('parent')


class ProductViewSet(PublicReadOnlyViewSet):
    queryset = Product.objects.none()
    serializer_class = s.ProductSerializer
    filters = {'brand': 'brand__key', 'category': 'category'}

    def base_queryset(self):
        return Product.objects.published().filter(brand__status='published').select_related('brand')


class ServiceViewSet(PublicReadOnlyViewSet):
    queryset = Service.objects.none()
    serializer_class = s.ServiceSerializer
    filters = {'brand': 'brand__key'}

    def base_queryset(self):
        return Service.objects.published().filter(brand__status='published').select_related('brand')


class PostViewSet(PublicReadOnlyViewSet):
    queryset = Post.objects.none()
    filters = {'lens': 'lens', 'author': 'author__slug'}

    def get_serializer_class(self):
        return s.PostDetailSerializer if self.action == 'retrieve' else s.PostListSerializer

    def base_queryset(self):
        return Post.objects.published().select_related('author')


class TeamMemberViewSet(PublicReadOnlyViewSet):
    queryset = TeamMember.objects.none()
    serializer_class = s.TeamMemberSerializer
    filters = {'department': 'department', 'tier': 'tier'}

    def base_queryset(self):
        return TeamMember.objects.published().filter(consent_to_publish=True)


class PartnerViewSet(PublicReadOnlyViewSet):
    queryset = Partner.objects.none()
    serializer_class = s.PartnerSerializer
    filters = {'tier': 'tier'}

    def base_queryset(self):
        return Partner.objects.published().filter(permission_to_display=True)


class RegionViewSet(PublicReadOnlyViewSet):
    queryset = Region.objects.none()
    serializer_class = s.RegionSerializer
    lookup_field = 'key'


class GalleryItemViewSet(PublicReadOnlyViewSet):
    queryset = GalleryItem.objects.none()
    serializer_class = s.GalleryItemSerializer
    lookup_field = 'pk'
    filters = {'category': 'category'}
