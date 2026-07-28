from django.contrib import admin

from kho_san_pham.models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'accounting_code', 'kiotviet_code', 'name',
        'product_type', 'unit', 'base_price', 'is_active', 'sync_source',
    )
    list_filter = ('product_type', 'is_active', 'sync_source')
    search_fields = ('code', 'accounting_code', 'kiotviet_code', 'name', 'bar_code')
    readonly_fields = ('kiotviet_id', 'synced_at', 'kv_modified_at', 'created_at', 'updated_at')
