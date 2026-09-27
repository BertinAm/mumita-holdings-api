from django.contrib import admin

from .models import Enquiry


@admin.register(Enquiry)
class EnquiryAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'enquiry_type', 'name', 'contact_kind', 'locale', 'status', 'assigned_to', 'created', 'retention_until')
    list_filter = ('enquiry_type', 'status', 'locale', 'contact_kind', 'staff_notified')
    search_fields = ('name', 'contact')
    date_hierarchy = 'created'
    list_select_related = ('assigned_to',)
    # Visitor-submitted content is read-only; staff change only the workflow fields.
    readonly_fields = (
        'name', 'contact', 'contact_kind', 'enquiry_type', 'message', 'locale', 'page',
        'ip_hash', 'staff_notified', 'created', 'retention_until',
    )
    fields = readonly_fields[:6] + ('status', 'assigned_to') + readonly_fields[6:]

    def has_add_permission(self, request):
        return False
