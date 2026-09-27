"""URL configuration.

The admin lives at DJANGO_ADMIN_URL (never the default /admin/), and the
public API is versioned under /api/v1/.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = 'Mumita Holdings CMS'
admin.site.site_title = 'Mumita CMS'
admin.site.index_title = 'Content'

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path('api/v1/', include('api.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
