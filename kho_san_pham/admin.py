from django.contrib import admin

from kho_san_pham.models import Product, ProductStyle, ProductType, ProductTypeKvMap


@admin.register(ProductType)
class ProductTypeAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'sort_order', 'is_active')
    search_fields = ('code', 'name')
    list_filter = ('is_active',)


@admin.register(ProductStyle)
class ProductStyleAdmin(admin.ModelAdmin):
    list_display = ('code', 'product_type', 'name', 'source', 'root_kiotviet_code', 'is_active')
    search_fields = ('code', 'name', 'root_kiotviet_code')
    list_filter = ('source', 'is_active', 'product_type')


@admin.register(ProductTypeKvMap)
class ProductTypeKvMapAdmin(admin.ModelAdmin):
    list_display = ('match_value', 'match_mode', 'product_type', 'priority', 'is_active')
    search_fields = ('match_value', 'notes')
    list_filter = ('match_mode', 'is_active', 'product_type')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'style_code', 'catalog_type', 'color_code', 'size_label', 'accounting_code', 'kiotviet_code',
        'name', 'product_type', 'unit', 'base_price', 'is_active', 'sync_source',
    )
    list_filter = ('product_type', 'catalog_type', 'is_active', 'sync_source')
    search_fields = ('code', 'style_code', 'color_code', 'size_label', 'accounting_code', 'kiotviet_code', 'name', 'bar_code')
    readonly_fields = ('sx_sku', 'kiotviet_id', 'synced_at', 'kv_modified_at', 'created_at', 'updated_at')
