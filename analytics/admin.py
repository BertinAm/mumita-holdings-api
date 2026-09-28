from django.contrib import admin

from .models import DailyVisit


@admin.register(DailyVisit)
class DailyVisitAdmin(admin.ModelAdmin):
    list_display = ('date', 'path', 'country', 'referrer_host', 'device', 'views')
    list_filter = ('device', 'country')
    date_hierarchy = 'date'
    search_fields = ('path', 'referrer_host')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
