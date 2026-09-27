from django.urls import include, path
from rest_framework.routers import DefaultRouter

from engagement.views import EnquiryView

from . import views

router = DefaultRouter(trailing_slash=True)
router.register('brands', views.BrandViewSet, basename='brand')
router.register('products', views.ProductViewSet, basename='product')
router.register('services', views.ServiceViewSet, basename='service')
router.register('posts', views.PostViewSet, basename='post')
router.register('team', views.TeamMemberViewSet, basename='team')
router.register('partners', views.PartnerViewSet, basename='partner')
router.register('regions', views.RegionViewSet, basename='region')
router.register('gallery', views.GalleryItemViewSet, basename='gallery')

app_name = 'api-v1'
urlpatterns = [
    path('enquiries/', EnquiryView.as_view(), name='enquiries'),
    path('', include(router.urls)),
]
