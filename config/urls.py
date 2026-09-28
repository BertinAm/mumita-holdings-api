"""URL configuration.

The admin lives at DJANGO_ADMIN_URL (never the default /admin/), and the
public API is versioned under /api/v1/.
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

admin.site.site_header = 'Mumita Holdings CMS'
admin.site.site_title = 'Mumita CMS'
admin.site.index_title = 'Content'

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path('api/v1/', include('api.urls')),
]

if settings.SERVE_MEDIA:
    # Development, or production when Apache is not serving MEDIA_ROOT itself
    # (DJANGO_SERVE_MEDIA=1). Only generated renditions and staff uploads live there.
    urlpatterns += [
        re_path(rf'^{settings.MEDIA_URL.lstrip("/")}(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    ]
