from django.contrib import admin

from kho_san_pham.models import (
    NegativeStockAlert,
    Product,
    ProductStyle,
    ProductType,
    ProductTypeKvMap,
    StockBalance,
    StockLedger,
    StockReceipt,
    StockReceiptLine,
    Warehouse,
)


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
        'name', 'product_type', 'unit', 'base_price', 'qty_on_hand', 'is_active', 'sync_source',
    )
    list_filter = ('product_type', 'catalog_type', 'is_active', 'sync_source')
    search_fields = ('code', 'style_code', 'color_code', 'size_label', 'accounting_code', 'kiotviet_code', 'name', 'bar_code')
    readonly_fields = ('sx_sku', 'kiotviet_id', 'synced_at', 'kv_modified_at', 'created_at', 'updated_at', 'qty_on_hand')


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'owner_system', 'is_active')
    list_filter = ('owner_system', 'is_active')
    search_fields = ('code', 'name')


@admin.register(StockBalance)
class StockBalanceAdmin(admin.ModelAdmin):
    list_display = ('product', 'warehouse', 'qty_on_hand', 'updated_at')
    list_filter = ('warehouse',)
    search_fields = ('product__code', 'product__name', 'warehouse__code')
    # Tồn chỉ được đổi qua post_movement — sửa tay ở admin là làm lệch sổ kho.
    readonly_fields = ('product', 'warehouse', 'qty_on_hand', 'updated_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StockLedger)
class StockLedgerAdmin(admin.ModelAdmin):
    list_display = (
        'occurred_at', 'product', 'warehouse', 'kind', 'qty_delta', 'balance_after',
        'source_system', 'source_doc_code', 'source_line_no', 'received_at',
    )
    list_filter = ('kind', 'source_system', 'warehouse', 'source_doc_type')
    search_fields = ('product__code', 'product__name', 'source_doc_code', 'actor')
    date_hierarchy = 'occurred_at'
    # Sổ kho là chỉ-ghi-thêm: sai thì ghi bút toán đảo, không sửa lịch sử.
    readonly_fields = [f.name for f in StockLedger._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(NegativeStockAlert)
class NegativeStockAlertAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'product_code', 'warehouse_code', 'balance_after', 'resolved_at')
    list_filter = ('warehouse_code', 'resolved_at')
    search_fields = ('product_code', 'warehouse_code')
    readonly_fields = ('ledger_entry', 'product_code', 'warehouse_code', 'balance_after', 'created_at')

    def has_add_permission(self, request):
        return False


class StockReceiptLineInline(admin.TabularInline):
    model = StockReceiptLine
    extra = 0
    readonly_fields = ('product', 'quantity', 'unit_cost', 'size_label', 'color_label', 'notes')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(StockReceipt)
class StockReceiptAdmin(admin.ModelAdmin):
    list_display = (
        'number', 'receipt_date', 'warehouse', 'production_order_code',
        'product_code', 'status', 'posted_at',
    )
    list_filter = ('status', 'warehouse', 'receipt_date')
    search_fields = ('number', 'production_order_code', 'product_code', 'notes')
    readonly_fields = (
        'number', 'receipt_date', 'warehouse', 'status', 'production_order_code',
        'product_code', 'fg_receipt', 'notes', 'created_by', 'posted_at', 'created_at',
    )
    inlines = [StockReceiptLineInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
