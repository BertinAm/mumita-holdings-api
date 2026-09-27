from django.contrib import admin
from modeltranslation.admin import TabbedTranslationAdmin

from common.admin import PUBLISH_ACTIONS

from .models import Product, Service


@admin.register(Product)
class ProductAdmin(TabbedTranslationAdmin):
    list_display = ('name', 'brand', 'category', 'weight', 'is_on_sale', 'status', 'sort_order')
    list_filter = ('brand', 'category', 'status', 'is_on_sale')
    list_editable = ('sort_order',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    list_select_related = ('brand',)
    actions = PUBLISH_ACTIONS


@admin.register(Service)
class ServiceAdmin(TabbedTranslationAdmin):
    list_display = ('name', 'brand', 'status', 'sort_order')
    list_filter = ('brand', 'status')
    list_editable = ('sort_order',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    list_select_related = ('brand',)
    actions = PUBLISH_ACTIONS
