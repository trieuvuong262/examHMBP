from django.contrib import admin

from kho_npl.models import (
    Material,
    MaterialBatch,
    MaterialGroup,
    MaterialCategory,
    MaterialColor,
    MaterialSpecification,
    MaterialSpecificationLevel,
    StockAdjustment,
    StockAdjustmentLine,
    StockBalance,
    StockIssue,
    StockIssueLine,
    StockLedger,
    StockReceipt,
    StockReceiptLine,
    Stocktake,
    StocktakeLine,
    Supplier,
    Unit,
    WarehouseLocation,
)


@admin.register(MaterialCategory)
class MaterialCategoryAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'sort_order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('code', 'name')


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_active')
    search_fields = ('code', 'name')


@admin.register(WarehouseLocation)
class WarehouseLocationAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_active')
    search_fields = ('code', 'name')


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'phone', 'is_active')
    search_fields = ('code', 'name')


class StockReceiptLineInline(admin.TabularInline):
    model = StockReceiptLine
    extra = 0


@admin.register(StockReceipt)
class StockReceiptAdmin(admin.ModelAdmin):
    list_display = ('number', 'receipt_date', 'supplier', 'status', 'created_at')
    list_filter = ('status', 'receipt_date')
    search_fields = ('number', 'po_number')
    inlines = [StockReceiptLineInline]


class StockIssueLineInline(admin.TabularInline):
    model = StockIssueLine
    extra = 0


@admin.register(StockIssue)
class StockIssueAdmin(admin.ModelAdmin):
    list_display = ('number', 'issue_date', 'issue_type', 'status', 'production_order')
    list_filter = ('status', 'issue_type')
    search_fields = ('number', 'production_order', 'product_code')
    inlines = [StockIssueLineInline]


@admin.register(MaterialColor)
class MaterialColorAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'hex_code', 'sort_order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('code', 'name')


class MaterialSpecificationLevelInline(admin.TabularInline):
    model = MaterialSpecificationLevel
    extra = 0


@admin.register(MaterialSpecification)
class MaterialSpecificationAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'conversion_formula', 'level_count', 'sort_order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('code', 'name')
    inlines = [MaterialSpecificationLevelInline]


@admin.register(MaterialGroup)
class MaterialGroupAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'category', 'stock_domain', 'is_active')
    list_filter = ('stock_domain', 'category', 'is_active')
    search_fields = ('code', 'name', 'category__name')


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'material_group', 'variant_group', 'category', 'department', 'color', 'specification', 'size', 'unit', 'primary_location', 'min_stock', 'is_active')
    list_filter = ('category', 'department', 'material_group', 'is_active')
    search_fields = ('code', 'name', 'material_group__code', 'material_group__name', 'variant_group', 'department', 'color__name', 'specification__name', 'size')


@admin.register(MaterialBatch)
class MaterialBatchAdmin(admin.ModelAdmin):
    list_display = ('material', 'code', 'unit_price', 'quantity', 'received_date', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('code', 'material__code', 'material__name')


@admin.register(StockBalance)
class StockBalanceAdmin(admin.ModelAdmin):
    list_display = ('material', 'location', 'quantity', 'updated_at')
    search_fields = ('material__code', 'material__name', 'location__code')


class StockAdjustmentLineInline(admin.TabularInline):
    model = StockAdjustmentLine
    extra = 0


@admin.register(StockAdjustment)
class StockAdjustmentAdmin(admin.ModelAdmin):
    list_display = ('number', 'adjust_date', 'status', 'proposed_by')
    list_filter = ('status',)
    inlines = [StockAdjustmentLineInline]


class StocktakeLineInline(admin.TabularInline):
    model = StocktakeLine
    extra = 0


@admin.register(Stocktake)
class StocktakeAdmin(admin.ModelAdmin):
    list_display = ('number', 'name', 'location', 'stocktake_date', 'status')
    list_filter = ('status',)
    inlines = [StocktakeLineInline]


@admin.register(StockLedger)
class StockLedgerAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'material', 'location', 'qty_delta', 'balance_after', 'ref_type', 'ref_number')
    list_filter = ('ref_type',)
    search_fields = ('material__code', 'ref_number')
