from django.urls import include, path
from rest_framework.routers import DefaultRouter, SimpleRouter

from accounts import views as accounts
from analytics.views import HitView, StatsView
from content import dashboard as content
from engagement import dashboard as engagement
from engagement.views import EnquiryView, TestimonialListView, TestimonialSubmitView

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

# Admins only (PLATFORM-CONTRACT "Admin").
manage = SimpleRouter(trailing_slash=True)
manage.register('login-events', accounts.LoginEventViewSet, basename='manage-login-event')
manage.register('users', accounts.UserViewSet, basename='manage-user')
manage.register('enquiries', engagement.ManageEnquiryViewSet, basename='manage-enquiry')
manage.register('testimonials', engagement.ManageTestimonialViewSet, basename='manage-testimonial')
manage.register('gallery', content.ManageGalleryViewSet, basename='manage-gallery')
manage.register('posts', content.ManagePostViewSet, basename='manage-post')

# Publishers and admins, own articles only (PLATFORM-CONTRACT "Publisher").
write = SimpleRouter(trailing_slash=True)
write.register('posts', content.WritePostViewSet, basename='write-post')

app_name = 'api-v1'
urlpatterns = [
    path('auth/csrf/', accounts.CsrfView.as_view(), name='auth-csrf'),
    path('auth/login/', accounts.LoginView.as_view(), name='auth-login'),
    path('auth/logout/', accounts.LogoutView.as_view(), name='auth-logout'),
    path('auth/me/', accounts.MeView.as_view(), name='auth-me'),
    path('auth/password/', accounts.PasswordView.as_view(), name='auth-password'),
    path('manage/stats/', StatsView.as_view(), name='manage-stats'),
    path('manage/uploads/', content.ManageUploadView.as_view(), name='manage-uploads'),
    path('manage/', include(manage.urls)),
    path('write/uploads/', content.WriteUploadView.as_view(), name='write-uploads'),
    path('write/', include(write.urls)),
    path('enquiries/', EnquiryView.as_view(), name='enquiries'),
    path('testimonials/', TestimonialListView.as_view(), name='testimonials'),
    path('testimonials/submit/', TestimonialSubmitView.as_view(), name='testimonials-submit'),
    path('analytics/hit/', HitView.as_view(), name='analytics-hit'),
    path('', include(router.urls)),
]
