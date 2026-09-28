from django.contrib import admin

from .models import Enquiry, EnquiryReply, Testimonial


@admin.register(Enquiry)
class EnquiryAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'enquiry_type', 'name', 'contact_kind', 'locale', 'status', 'assigned_to', 'created', 'retention_until')
    list_filter = ('enquiry_type', 'source', 'status', 'locale', 'contact_kind', 'staff_notified')
    search_fields = ('name', 'contact')
    date_hierarchy = 'created'
    list_select_related = ('assigned_to',)
    # Visitor-submitted content is read-only; staff change only the workflow fields.
    readonly_fields = (
        'name', 'contact', 'contact_kind', 'enquiry_type', 'message', 'source', 'topic', 'locale', 'page',
        'ip_hash', 'staff_notified', 'created', 'retention_until',
    )
    fields = readonly_fields[:8] + ('status', 'assigned_to') + readonly_fields[8:]

    def has_add_permission(self, request):
        return False


@admin.register(EnquiryReply)
class EnquiryReplyAdmin(admin.ModelAdmin):
    list_display = ('enquiry', 'author', 'emailed', 'created')
    readonly_fields = ('enquiry', 'author', 'message', 'emailed', 'created')

    def has_add_permission(self, request):
        return False


@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ('name', 'role_or_place', 'status', 'consent', 'created')
    list_filter = ('status', 'consent')
    search_fields = ('name', 'quote')
    readonly_fields = ('ip_hash', 'locale', 'created', 'updated', 'reviewed_by', 'reviewed_at')
