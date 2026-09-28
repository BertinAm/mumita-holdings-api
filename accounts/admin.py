from django.contrib import admin

from .models import LoginEvent, Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'must_change_password')
    search_fields = ('name', 'user__email')


@admin.register(LoginEvent)
class LoginEventAdmin(admin.ModelAdmin):
    list_display = ('created', 'realm', 'username', 'success', 'outcome', 'user_agent_family')
    list_filter = ('realm', 'success', 'outcome')
    search_fields = ('username',)
    date_hierarchy = 'created'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
