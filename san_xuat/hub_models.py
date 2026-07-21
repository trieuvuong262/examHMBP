"""Model nghiệp vụ hub Sản xuất (kế hoạch / điều phối / QC / giá thành KH).

Dữ liệu demo: is_demo=True — không thay thế kho_npl / KiotViet.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class DemoMarkedModel(models.Model):
    is_demo = models.BooleanField(default=False, db_index=True, verbose_name='Dữ liệu demo')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(app_label)s_%(class)s_created',
        verbose_name='Người tạo',
    )

    class Meta:
        abstract = True


# --- Kế hoạch ---


class SxOverallPlan(DemoMarkedModel):
    STATUS_DRAFT = 'draft'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_DONE = 'done'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Nháp'),
        (STATUS_CONFIRMED, 'Đã xác nhận'),
        (STATUS_DONE, 'Hoàn thành'),
        (STATUS_CANCELLED, 'Hủy'),
    ]

    code = models.CharField(max_length=40, unique=True, verbose_name='Mã KHTT')
    name = models.CharField(max_length=200, verbose_name='Tên kế hoạch')
    date_from = models.DateField(verbose_name='Từ ngày')
    date_to = models.DateField(verbose_name='Đến ngày')
    SOURCE_FORECAST = 'forecast'
    SOURCE_SALES_ORDER = 'sales_order'
    SOURCE_CHOICES = [
        (SOURCE_FORECAST, 'Dự báo / nhập tay'),
        (SOURCE_SALES_ORDER, 'Từ đơn KV'),
    ]
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_FORECAST)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_from', 'code']
        verbose_name = 'Kế hoạch tổng thể'
        verbose_name_plural = 'Kế hoạch tổng thể'

    def __str__(self):
        return f'{self.code} — {self.name}'


class SxOverallPlanLine(models.Model):
    plan = models.ForeignKey(SxOverallPlan, on_delete=models.CASCADE, related_name='lines')
    product_code = models.CharField(max_length=60, db_index=True)
    product_name = models.CharField(max_length=255, blank=True, default='')
    qty_required = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    qty_planned = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    capacity_per_day = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    kv_order_kiotviet_id = models.BigIntegerField(null=True, blank=True, verbose_name='KV order id')
    kv_order_code = models.CharField(max_length=64, blank=True, default='', verbose_name='Mã đơn KV')

    class Meta:
        ordering = ['id']
        verbose_name = 'Dòng KHTT'
        verbose_name_plural = 'Dòng KHTT'


class SxDetailPlan(DemoMarkedModel):
    code = models.CharField(max_length=40, unique=True, verbose_name='Mã KHCT')
    name = models.CharField(max_length=200, verbose_name='Tên')
    overall_plan = models.ForeignKey(
        SxOverallPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='detail_plans',
    )
    date_from = models.DateField()
    date_to = models.DateField()
    status = models.CharField(max_length=20, choices=SxOverallPlan.STATUS_CHOICES, default=SxOverallPlan.STATUS_DRAFT)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_from', 'code']
        verbose_name = 'Kế hoạch chi tiết'
        verbose_name_plural = 'Kế hoạch chi tiết'

    def __str__(self):
        return self.code


class SxDetailPlanLine(models.Model):
    plan = models.ForeignKey(SxDetailPlan, on_delete=models.CASCADE, related_name='lines')
    plan_date = models.DateField()
    product_code = models.CharField(max_length=60, db_index=True)
    product_name = models.CharField(max_length=255, blank=True, default='')
    qty = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    team_label = models.CharField(max_length=80, blank=True, default='', verbose_name='Tổ/chuyền')
    work_center = models.ForeignKey(
        'san_xuat.SxWorkCenter',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='detail_plan_lines',
        verbose_name='Năng lực SX',
    )

    class Meta:
        ordering = ['plan_date', 'id']
        verbose_name = 'Dòng KHCT'
        verbose_name_plural = 'Dòng KHCT'


class SxMaterialPlan(DemoMarkedModel):
    code = models.CharField(max_length=40, unique=True, verbose_name='Mã kế hoạch nguyên phụ liệu')
    name = models.CharField(max_length=200, verbose_name='Tên')
    overall_plan = models.ForeignKey(
        SxOverallPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='material_plans',
    )
    status = models.CharField(max_length=20, choices=SxOverallPlan.STATUS_CHOICES, default=SxOverallPlan.STATUS_DRAFT)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Kế hoạch NPL'
        verbose_name_plural = 'Kế hoạch NPL'

    def __str__(self):
        return self.code


class SxMaterialPlanLine(models.Model):
    plan = models.ForeignKey(SxMaterialPlan, on_delete=models.CASCADE, related_name='lines')
    material_code = models.CharField(max_length=60, db_index=True)
    material_name = models.CharField(max_length=255, blank=True, default='')
    qty_required = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0'))
    qty_on_hand = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0'))
    qty_shortfall = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0'))
    qty_expected_inbound = models.DecimalField(
        max_digits=14, decimal_places=4, default=Decimal('0'), verbose_name='Dự kiến về (PO mở)',
    )

    class Meta:
        ordering = ['id']
        verbose_name = 'Dòng kế hoạch nguyên phụ liệu'
        verbose_name_plural = 'Dòng kế hoạch nguyên phụ liệu'


class SxNplPurchaseRequest(DemoMarkedModel):
    STATUS_DRAFT = 'draft'
    STATUS_SUBMITTED = 'submitted'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Nháp'),
        (STATUS_SUBMITTED, 'Đã gửi'),
        (STATUS_APPROVED, 'Đã duyệt'),
        (STATUS_REJECTED, 'Từ chối'),
    ]

    code = models.CharField(max_length=40, unique=True, verbose_name='Mã YCM')
    material_plan = models.ForeignKey(
        SxMaterialPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='purchase_requests',
    )
    request_date = models.DateField(null=True, blank=True, verbose_name='Ngày YC')
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Yêu cầu mua NPL'
        verbose_name_plural = 'Yêu cầu mua NPL'

    def __str__(self):
        return self.code


class SxNplPurchaseRequestLine(models.Model):
    request = models.ForeignKey(SxNplPurchaseRequest, on_delete=models.CASCADE, related_name='lines')
    material_code = models.CharField(max_length=60)
    material_name = models.CharField(max_length=255, blank=True, default='')
    qty = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0'))

    class Meta:
        ordering = ['id']


class SxPurchaseOrder(DemoMarkedModel):
    STATUS_DRAFT = 'draft'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_RECEIVED = 'received'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Nháp'),
        (STATUS_CONFIRMED, 'Đã xác nhận'),
        (STATUS_RECEIVED, 'Đã nhập'),
    ]

    code = models.CharField(max_length=40, unique=True, verbose_name='Mã DMH')
    supplier_name = models.CharField(max_length=200, blank=True, default='')
    purchase_request = models.ForeignKey(
        SxNplPurchaseRequest, on_delete=models.SET_NULL, null=True, blank=True, related_name='purchase_orders',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    kv_purchase_kiotviet_id = models.BigIntegerField(null=True, blank=True, verbose_name='KV purchase id')
    kv_purchase_code = models.CharField(max_length=64, blank=True, default='', verbose_name='Mã phiếu nhập KV')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Đơn mua hàng'
        verbose_name_plural = 'Đơn mua hàng'

    def __str__(self):
        return self.code


class SxPurchaseOrderLine(models.Model):
    order = models.ForeignKey(SxPurchaseOrder, on_delete=models.CASCADE, related_name='lines')
    material_code = models.CharField(max_length=60)
    material_name = models.CharField(max_length=255, blank=True, default='')
    qty_ordered = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0'))
    qty_received = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0'))

    class Meta:
        ordering = ['id']


# --- Điều phối ---


class SxProductionOrder(DemoMarkedModel):
    STATUS_DRAFT = 'draft'
    STATUS_RELEASED = 'released'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_DONE = 'done'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Nháp'),
        (STATUS_RELEASED, 'Đã phát hành'),
        (STATUS_IN_PROGRESS, 'Đang SX'),
        (STATUS_DONE, 'Hoàn thành'),
        (STATUS_CANCELLED, 'Hủy'),
    ]

    code = models.CharField(max_length=40, unique=True, verbose_name='Mã lệnh sản xuất')
    product_code = models.CharField(max_length=60, db_index=True)
    product_name = models.CharField(max_length=255, blank=True, default='')
    detail_plan = models.ForeignKey(
        SxDetailPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='production_orders',
    )
    bom_version = models.ForeignKey(
        'san_xuat.BomVersion', on_delete=models.SET_NULL, null=True, blank=True, related_name='production_orders',
    )
    qty = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    qty_done = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    order_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    planned_start = models.DateField(null=True, blank=True)
    planned_end = models.DateField(null=True, blank=True)
    team_label = models.CharField(max_length=80, blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    is_sample = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name='Lệnh sản xuất mẫu',
        help_text='Tách khỏi lệnh sản xuất đại trà (có thể lọc khi tính năng lực).',
    )
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-order_date', 'code']
        verbose_name = 'Lệnh sản xuất'
        verbose_name_plural = 'Lệnh sản xuất'

    def __str__(self):
        return self.code


class SxDisassemblyOrder(DemoMarkedModel):
    STATUS_DRAFT = 'draft'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Nháp'),
        (STATUS_CONFIRMED, 'Đã xác nhận'),
        (STATUS_CANCELLED, 'Hủy'),
    ]

    code = models.CharField(max_length=40, unique=True, verbose_name='Mã LTD')
    production_order = models.ForeignKey(
        SxProductionOrder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='disassembly_orders',
        verbose_name='Lệnh sản xuất nguồn',
    )
    product_code = models.CharField(max_length=60, db_index=True)
    product_name = models.CharField(max_length=255, blank=True, default='')
    qty = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    order_date = models.DateField()
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True,
    )
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-order_date']
        verbose_name = 'Lệnh tháo dỡ'
        verbose_name_plural = 'Lệnh tháo dỡ'

    def __str__(self):
        return self.code


class SxDisassemblyOrderLine(models.Model):
    """NVL / BTP thu hồi từ lệnh tháo dỡ."""

    order = models.ForeignKey(
        SxDisassemblyOrder, on_delete=models.CASCADE, related_name='lines',
    )
    material_code = models.CharField(max_length=60)
    material_name = models.CharField(max_length=255, blank=True, default='')
    qty = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0'))
    notes = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        ordering = ['id']
        verbose_name = 'Dòng tháo dỡ'
        verbose_name_plural = 'Dòng tháo dỡ'


class SxMaterialIssueRequest(DemoMarkedModel):
    code = models.CharField(max_length=40, unique=True, verbose_name='Mã yêu cầu xuất')
    production_order = models.ForeignKey(
        SxProductionOrder, on_delete=models.CASCADE, related_name='material_issue_requests',
    )
    # Liên kết phiếu xuất NPL thật trên kho_npl sau khi duyệt YCX.
    stock_issue = models.ForeignKey(
        'kho_npl.StockIssue',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='material_issue_requests',
        verbose_name='Phiếu xuất NPL',
    )
    status = models.CharField(max_length=20, default='draft')
    request_date = models.DateField()
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-request_date']
        verbose_name = 'Yêu cầu xuất vật tư'
        verbose_name_plural = 'Yêu cầu xuất vật tư'

    def __str__(self):
        return self.code


class SxMaterialIssueRequestLine(models.Model):
    request = models.ForeignKey(SxMaterialIssueRequest, on_delete=models.CASCADE, related_name='lines')
    material_code = models.CharField(max_length=60)
    material_name = models.CharField(max_length=255, blank=True, default='')
    qty_requested = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0'))
    qty_issued = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0'))
    preferred_location = models.ForeignKey(
        'kho_npl.WarehouseLocation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ycx_preferred_lines',
        verbose_name='Vị trí ưu tiên',
    )

    class Meta:
        ordering = ['id']


class SxProductionStat(DemoMarkedModel):
    STATUS_DRAFT = 'draft'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Nháp'),
        (STATUS_CONFIRMED, 'Đã xác nhận'),
    ]

    code = models.CharField(max_length=40, unique=True, verbose_name='Mã thống kê sản xuất')
    production_order = models.ForeignKey(
        SxProductionOrder, on_delete=models.CASCADE, related_name='production_stats',
    )
    stat_date = models.DateField()
    process_name = models.CharField(max_length=120, blank=True, default='')
    qty_good = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    qty_defect = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    team_label = models.CharField(max_length=80, blank=True, default='')
    sku_code = models.CharField(max_length=60, blank=True, default='', verbose_name='SKU')
    size_label = models.CharField(max_length=40, blank=True, default='', verbose_name='Size')
    color_label = models.CharField(max_length=40, blank=True, default='', verbose_name='Màu')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-stat_date']
        verbose_name = 'Thống kê sản xuất'
        verbose_name_plural = 'Thống kê sản xuất'

    def __str__(self):
        return self.code


class SxFgReceiptRequest(DemoMarkedModel):
    STATUS_DRAFT = 'draft'
    STATUS_SUBMITTED = 'submitted'
    STATUS_DONE = 'done'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Nháp'),
        (STATUS_SUBMITTED, 'Đã gửi'),
        (STATUS_DONE, 'Hoàn thành'),
        (STATUS_CANCELLED, 'Hủy'),
    ]

    code = models.CharField(max_length=40, unique=True, verbose_name='Mã yêu cầu nhập thành phẩm')
    production_order = models.ForeignKey(
        SxProductionOrder, on_delete=models.CASCADE, related_name='fg_receipt_requests',
    )
    production_stat = models.ForeignKey(
        SxProductionStat, on_delete=models.SET_NULL, null=True, blank=True, related_name='fg_receipt_requests',
        verbose_name='Thống kê sản xuất nguồn',
    )
    request_date = models.DateField()
    qty = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    kv_purchase_kiotviet_id = models.BigIntegerField(null=True, blank=True, verbose_name='KV purchase id')
    kv_purchase_code = models.CharField(max_length=64, blank=True, default='', verbose_name='Mã phiếu nhập KV')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-request_date']
        verbose_name = 'Yêu cầu nhập thành phẩm'
        verbose_name_plural = 'Yêu cầu nhập thành phẩm'

    def __str__(self):
        return self.code


class SxNplSurplus(DemoMarkedModel):
    STATUS_DRAFT = 'draft'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Nháp'),
        (STATUS_CONFIRMED, 'Đã nhập kho'),
        (STATUS_CANCELLED, 'Hủy'),
    ]

    code = models.CharField(max_length=40, unique=True, verbose_name='Mã NPL thừa')
    production_order = models.ForeignKey(
        SxProductionOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name='npl_surplus_records',
    )
    disassembly_order = models.ForeignKey(
        SxDisassemblyOrder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='surplus_records',
        verbose_name='LTD nguồn',
    )
    material_code = models.CharField(max_length=60)
    material_name = models.CharField(max_length=255, blank=True, default='')
    qty = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0'))
    recorded_at = models.DateField()
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True,
    )
    stock_adjustment = models.ForeignKey(
        'kho_npl.StockAdjustment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='npl_surplus_records',
        verbose_name='Phiếu ĐC kho',
    )
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-recorded_at']
        verbose_name = 'NPL thừa'
        verbose_name_plural = 'NPL thừa'

    def __str__(self):
        return self.code


class SxWipHandover(DemoMarkedModel):
    STATUS_PENDING = 'pending'
    STATUS_DONE = 'done'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Chờ bàn giao'),
        (STATUS_DONE, 'Đã bàn giao'),
        (STATUS_REJECTED, 'Từ chối'),
    ]

    code = models.CharField(max_length=40, unique=True, verbose_name='Mã bàn giao')
    production_order = models.ForeignKey(
        SxProductionOrder, on_delete=models.CASCADE, related_name='wip_handovers',
    )
    from_process = models.CharField(max_length=120, blank=True, default='')
    to_process = models.CharField(max_length=120, blank=True, default='')
    qty = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    handover_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-handover_date']
        verbose_name = 'Bàn giao bán thành phẩm'
        verbose_name_plural = 'Bàn giao bán thành phẩm'

    def __str__(self):
        return self.code


class SxWipReturn(DemoMarkedModel):
    STATUS_DRAFT = 'draft'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Nháp'),
        (STATUS_CONFIRMED, 'Đã xác nhận'),
        (STATUS_CANCELLED, 'Hủy'),
    ]

    code = models.CharField(max_length=40, unique=True, verbose_name='Mã trả bán thành phẩm')
    handover = models.ForeignKey(
        SxWipHandover, on_delete=models.SET_NULL, null=True, blank=True, related_name='returns',
    )
    production_order = models.ForeignKey(
        SxProductionOrder, on_delete=models.CASCADE, related_name='wip_returns',
    )
    from_process = models.CharField(
        max_length=120, blank=True, default='', verbose_name='Từ công đoạn (đang giữ)',
    )
    to_process = models.CharField(
        max_length=120, blank=True, default='', verbose_name='Về công đoạn (sửa)',
    )
    qty = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    return_date = models.DateField()
    reason = models.CharField(max_length=255, blank=True, default='')
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True,
    )
    notes = models.TextField(blank=True, default='')
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-return_date']
        verbose_name = 'Trả lại bán thành phẩm'
        verbose_name_plural = 'Trả lại bán thành phẩm'

    def __str__(self):
        return self.code


class SxWipBalance(DemoMarkedModel):
    production_order = models.ForeignKey(
        SxProductionOrder, on_delete=models.CASCADE, related_name='wip_balances',
    )
    process_name = models.CharField(max_length=120, verbose_name='Công đoạn')
    qty = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['production_order_id', 'process_name']
        verbose_name = 'Tồn bán thành phẩm theo công đoạn'
        verbose_name_plural = 'Tồn bán thành phẩm theo công đoạn'
        constraints = [
            models.UniqueConstraint(
                fields=['production_order', 'process_name'],
                name='uniq_sx_wip_balance_mo_process',
            ),
        ]

    def __str__(self):
        return f'{self.production_order_id} · {self.process_name}: {self.qty}'


# --- QC ---


class SxQcCriteriaGroup(DemoMarkedModel):
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']
        verbose_name = 'Nhóm tiêu chí QC'
        verbose_name_plural = 'Nhóm tiêu chí QC'

    def __str__(self):
        return self.name


class SxQcCriteria(DemoMarkedModel):
    KIND_QUALITATIVE = 'qualitative'
    KIND_QUANTITATIVE = 'quantitative'
    KIND_CHOICES = [
        (KIND_QUALITATIVE, 'Định tính'),
        (KIND_QUANTITATIVE, 'Định lượng'),
    ]

    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=200)
    group = models.ForeignKey(SxQcCriteriaGroup, on_delete=models.PROTECT, related_name='criteria')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_QUALITATIVE)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']
        verbose_name = 'Tiêu chí QC'
        verbose_name_plural = 'Tiêu chí QC'

    def __str__(self):
        return self.name


class SxQcSamplingMethod(DemoMarkedModel):
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=200)
    method_type = models.CharField(max_length=20, default='fixed_qty')
    sample_value = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('5'))
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']
        verbose_name = 'Phương pháp chọn mẫu'
        verbose_name_plural = 'Phương pháp chọn mẫu'

    def __str__(self):
        return self.name


class SxQcStandardSet(DemoMarkedModel):
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=200)
    product_code = models.CharField(max_length=60, blank=True, default='')
    stage_name = models.CharField(max_length=120, blank=True, default='', verbose_name='Công đoạn')
    defect_tolerance_pct = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal('5'),
        verbose_name='Ngưỡng lỗi cho phép (%)',
    )
    sampling_method = models.ForeignKey(
        SxQcSamplingMethod, on_delete=models.PROTECT, related_name='standard_sets',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']
        verbose_name = 'Bộ tiêu chuẩn QC'
        verbose_name_plural = 'Bộ tiêu chuẩn QC'

    def __str__(self):
        return self.name


class SxQcStandardCriteria(models.Model):
    standard_set = models.ForeignKey(SxQcStandardSet, on_delete=models.CASCADE, related_name='criteria_links')
    criteria = models.ForeignKey(SxQcCriteria, on_delete=models.PROTECT, related_name='standard_links')
    sort_order = models.PositiveSmallIntegerField(default=0)
    min_value = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    max_value = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)

    class Meta:
        ordering = ['sort_order', 'id']
        unique_together = [('standard_set', 'criteria')]
        verbose_name = 'Tiêu chí trong bộ TC'
        verbose_name_plural = 'Tiêu chí trong bộ TC'


class SxQcDefectGroup(DemoMarkedModel):
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']
        verbose_name = 'Nhóm lỗi QC'
        verbose_name_plural = 'Nhóm lỗi QC'

    def __str__(self):
        return self.name


class SxQcDefect(DemoMarkedModel):
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=200)
    group = models.ForeignKey(SxQcDefectGroup, on_delete=models.PROTECT, related_name='defects')
    severity = models.CharField(max_length=20, default='minor')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']
        verbose_name = 'Lỗi QC'
        verbose_name_plural = 'Lỗi QC'

    def __str__(self):
        return self.name


class SxQcRequest(DemoMarkedModel):
    code = models.CharField(max_length=40, unique=True, verbose_name='Mã YCKT')
    production_order = models.ForeignKey(
        SxProductionOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name='qc_requests',
    )
    production_stat = models.ForeignKey(
        SxProductionStat, on_delete=models.SET_NULL, null=True, blank=True, related_name='qc_requests',
        verbose_name='Thống kê sản xuất nguồn',
    )
    product_code = models.CharField(max_length=60, db_index=True)
    product_name = models.CharField(max_length=255, blank=True, default='')
    stage_name = models.CharField(max_length=120, blank=True, default='')
    sku_code = models.CharField(max_length=60, blank=True, default='', verbose_name='SKU')
    size_label = models.CharField(max_length=40, blank=True, default='', verbose_name='Size')
    color_label = models.CharField(max_length=40, blank=True, default='', verbose_name='Màu')
    qty = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    request_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, default='open')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-request_date']
        verbose_name = 'Yêu cầu kiểm tra'
        verbose_name_plural = 'Yêu cầu kiểm tra'

    def __str__(self):
        return self.code


class SxQcInspection(DemoMarkedModel):
    RESULT_PASS = 'pass'
    RESULT_FAIL = 'fail'
    RESULT_PENDING = 'pending'
    RESULT_CHOICES = [
        (RESULT_PASS, 'Đạt'),
        (RESULT_FAIL, 'Không đạt'),
        (RESULT_PENDING, 'Chờ'),
    ]

    code = models.CharField(max_length=40, unique=True, verbose_name='Mã PKT')
    qc_request = models.ForeignKey(
        SxQcRequest, on_delete=models.SET_NULL, null=True, blank=True, related_name='inspections',
    )
    standard_set = models.ForeignKey(
        SxQcStandardSet, on_delete=models.SET_NULL, null=True, blank=True, related_name='inspections',
    )
    inspected_at = models.DateField()
    qty_sample = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    qty_pass = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    qty_fail = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    result = models.CharField(max_length=20, choices=RESULT_CHOICES, default=RESULT_PENDING)
    status = models.CharField(max_length=20, default='done')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-inspected_at']
        verbose_name = 'Phiếu kiểm tra'
        verbose_name_plural = 'Phiếu kiểm tra'

    def __str__(self):
        return self.code


class SxQcInspectionCriteriaLine(models.Model):
    inspection = models.ForeignKey(
        SxQcInspection, on_delete=models.CASCADE, related_name='criteria_lines',
    )
    criteria = models.ForeignKey(SxQcCriteria, on_delete=models.PROTECT, related_name='inspection_lines')
    value_text = models.CharField(max_length=255, blank=True, default='')
    value_number = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    is_pass = models.BooleanField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        ordering = ['id']
        unique_together = [('inspection', 'criteria')]
        verbose_name = 'Dòng tiêu chí PKT'
        verbose_name_plural = 'Dòng tiêu chí PKT'


class SxQcInspectionDefectLine(models.Model):
    inspection = models.ForeignKey(
        SxQcInspection, on_delete=models.CASCADE, related_name='defect_lines',
    )
    defect = models.ForeignKey(SxQcDefect, on_delete=models.PROTECT, related_name='inspection_lines')
    qty = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    notes = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        ordering = ['id']
        verbose_name = 'Dòng lỗi PKT'
        verbose_name_plural = 'Dòng lỗi PKT'


class SxQcAlert(DemoMarkedModel):
    TYPE_DEFECT_RATE = 'defect_rate_exceeded'
    TYPE_QC_FAIL = 'qc_inspection_fail'
    TYPE_CHOICES = [
        (TYPE_DEFECT_RATE, 'Tỷ lệ lỗi vượt ngưỡng'),
        (TYPE_QC_FAIL, 'Phiếu kiểm tra không đạt'),
    ]

    STATUS_OPEN = 'open'
    STATUS_ACK = 'acknowledged'
    STATUS_CLOSED = 'closed'
    STATUS_CHOICES = [
        (STATUS_OPEN, 'Mở'),
        (STATUS_ACK, 'Đã xử lý'),
        (STATUS_CLOSED, 'Đóng'),
    ]

    code = models.CharField(max_length=40, unique=True, verbose_name='Mã cảnh báo')
    alert_type = models.CharField(max_length=30, choices=TYPE_CHOICES, db_index=True)
    production_order = models.ForeignKey(
        SxProductionOrder, on_delete=models.CASCADE, related_name='qc_alerts',
    )
    production_stat = models.ForeignKey(
        SxProductionStat, on_delete=models.SET_NULL, null=True, blank=True, related_name='qc_alerts',
    )
    qc_request = models.ForeignKey(
        SxQcRequest, on_delete=models.SET_NULL, null=True, blank=True, related_name='alerts',
    )
    qc_inspection = models.ForeignKey(
        SxQcInspection, on_delete=models.SET_NULL, null=True, blank=True, related_name='alerts',
    )
    process_name = models.CharField(max_length=120, blank=True, default='')
    defect_rate = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0'))
    tolerance_limit = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('5'))
    qty_good = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    qty_defect = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    message = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Cảnh báo QC'
        verbose_name_plural = 'Cảnh báo QC'

    def __str__(self):
        return self.code


# --- Giá thành kế hoạch ---


class SxStandardCostSheet(DemoMarkedModel):
    STATUS_DRAFT = 'draft'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Nháp'),
        (STATUS_CONFIRMED, 'Đã chốt'),
    ]

    code = models.CharField(max_length=40, unique=True, verbose_name='Mã GTDM')
    name = models.CharField(max_length=200)
    date_from = models.DateField()
    date_to = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_from']
        verbose_name = 'Bảng giá thành định mức'
        verbose_name_plural = 'Bảng giá thành định mức'

    def __str__(self):
        return self.code


class SxStandardCostLine(models.Model):
    sheet = models.ForeignKey(SxStandardCostSheet, on_delete=models.CASCADE, related_name='lines')
    product_code = models.CharField(max_length=60, db_index=True)
    product_name = models.CharField(max_length=255, blank=True, default='')
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    material_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    labor_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    overhead_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))

    class Meta:
        ordering = ['product_code']


class SxOrderPlanCost(DemoMarkedModel):
    STATUS_DRAFT = 'draft'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Nháp'),
        (STATUS_CONFIRMED, 'Đã chốt'),
    ]

    code = models.CharField(max_length=40, unique=True, verbose_name='Mã GTĐH')
    name = models.CharField(max_length=200)
    kv_order_code = models.CharField(max_length=80, blank=True, default='', verbose_name='Mã đơn KV')
    kv_order_kiotviet_id = models.BigIntegerField(null=True, blank=True, verbose_name='KV order id')
    date_from = models.DateField()
    date_to = models.DateField()
    total_cost = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0'))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_from']
        verbose_name = 'Giá thành KH theo đơn'
        verbose_name_plural = 'Giá thành KH theo đơn'

    def __str__(self):
        return self.code


class SxOrderPlanCostLine(models.Model):
    sheet = models.ForeignKey(SxOrderPlanCost, on_delete=models.CASCADE, related_name='lines')
    product_code = models.CharField(max_length=60, db_index=True)
    product_name = models.CharField(max_length=255, blank=True, default='')
    qty = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    extra_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    line_cost = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0'))

    class Meta:
        ordering = ['id']


class SxCostType(DemoMarkedModel):
    """Loại chi phí thêm cấu hình được (C4) — cột động trên GTKH theo đơn."""

    code = models.CharField(max_length=40, unique=True, verbose_name='Mã loại CP')
    name = models.CharField(max_length=120, verbose_name='Tên loại CP')
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveIntegerField(default=100)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sort_order', 'code']
        verbose_name = 'Loại chi phí thêm'
        verbose_name_plural = 'Loại chi phí thêm'

    def __str__(self):
        return f'{self.code} — {self.name}'


class SxOrderPlanCostLineExtra(models.Model):
    line = models.ForeignKey(
        SxOrderPlanCostLine, on_delete=models.CASCADE, related_name='typed_extras',
    )
    cost_type = models.ForeignKey(
        SxCostType, on_delete=models.PROTECT, related_name='order_line_extras',
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))

    class Meta:
        ordering = ['cost_type__sort_order', 'id']
        verbose_name = 'CP thêm theo loại'
        verbose_name_plural = 'CP thêm theo loại'
        constraints = [
            models.UniqueConstraint(
                fields=['line', 'cost_type'],
                name='uniq_order_line_cost_type',
            ),
        ]


# --- Giai đoạn 3 / ops (0014–0018) ---


class SxWorkCenter(DemoMarkedModel):
    code = models.CharField(max_length=40, unique=True, verbose_name='Mã tổ/chuyền')
    name = models.CharField(max_length=120)
    capacity_per_day = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'), verbose_name='Năng lực/ngày',
    )
    uom_label = models.CharField(max_length=40, blank=True, default='SP')
    team_label = models.CharField(
        max_length=80,
        blank=True,
        default='',
        verbose_name='Nhãn tổ (khớp thống kê sản xuất)',
        help_text='Khớp field team_label trên TKSX để tính tải thực tế.',
    )
    is_active = models.BooleanField(default=True, db_index=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['code']
        verbose_name = 'Năng lực SX'
        verbose_name_plural = 'Năng lực SX'

    def __str__(self):
        return f'{self.code} — {self.name}'


class SxPackingRecord(DemoMarkedModel):
    STATUS_DRAFT = 'draft'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Nháp'),
        (STATUS_CONFIRMED, 'Đã xác nhận'),
    ]

    code = models.CharField(max_length=40, unique=True, verbose_name='Mã ĐG')
    production_order = models.ForeignKey(
        SxProductionOrder, on_delete=models.CASCADE, related_name='packing_records',
    )
    fg_receipt = models.ForeignKey(
        SxFgReceiptRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='packing_records',
    )
    pack_date = models.DateField()
    qty = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    carton_count = models.PositiveIntegerField(default=0, verbose_name='Số thùng/kiện')
    lot_code = models.CharField(max_length=60, blank=True, default='')
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True,
    )
    notes = models.TextField(blank=True, default='')
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-pack_date', '-pk']
        verbose_name = 'Đóng gói'
        verbose_name_plural = 'Đóng gói'

    def __str__(self):
        return self.code


class SxPackingLine(models.Model):
    packing = models.ForeignKey(SxPackingRecord, on_delete=models.CASCADE, related_name='lines')
    sku_code = models.CharField(max_length=60, blank=True, default='', verbose_name='SKU')
    size_label = models.CharField(max_length=40, blank=True, default='', verbose_name='Size')
    color_label = models.CharField(max_length=40, blank=True, default='', verbose_name='Màu')
    qty = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    carton_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['pk']
        verbose_name = 'Dòng đóng gói'
        verbose_name_plural = 'Dòng đóng gói'


class SxSubcontractOrder(DemoMarkedModel):
    STATUS_DRAFT = 'draft'
    STATUS_SENT = 'sent'
    STATUS_RECEIVED = 'received'
    STATUS_DONE = 'done'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Nháp'),
        (STATUS_SENT, 'Đã gửi GC'),
        (STATUS_RECEIVED, 'Đã nhận lại'),
        (STATUS_DONE, 'Hoàn thành'),
        (STATUS_CANCELLED, 'Hủy'),
    ]

    code = models.CharField(max_length=40, unique=True, verbose_name='Mã GC')
    production_order = models.ForeignKey(
        SxProductionOrder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subcontract_orders',
    )
    vendor_name = models.CharField(max_length=200, verbose_name='Đơn vị gia công')
    product_code = models.CharField(max_length=60, db_index=True)
    product_name = models.CharField(max_length=255, blank=True, default='')
    process_name = models.CharField(max_length=120, blank=True, default='')
    qty = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    qty_received = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'), verbose_name='SL nhận lại',
    )
    service_fee = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name='Phí gia công (VNĐ)',
        help_text='Chi phí GC đưa vào giá thành thực tế.',
    )
    order_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True,
    )
    stock_issue = models.ForeignKey(
        'kho_npl.StockIssue',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sx_subcontract_orders',
        verbose_name='Phiếu xuất kho (gửi GC)',
    )
    stock_adjustment = models.ForeignKey(
        'kho_npl.StockAdjustment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sx_subcontract_orders',
        verbose_name='Phiếu ĐC kho (nhận về)',
    )
    notes = models.TextField(blank=True, default='')
    sent_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-order_date', '-pk']
        verbose_name = 'Thuê gia công'
        verbose_name_plural = 'Thuê gia công'

    def __str__(self):
        return self.code


class SxSubcontractMaterialLine(models.Model):
    DIRECTION_OUT = 'out'
    DIRECTION_IN = 'in'
    DIRECTION_CHOICES = [
        (DIRECTION_OUT, 'Xuất đi GC'),
        (DIRECTION_IN, 'Nhận về'),
    ]

    order = models.ForeignKey(
        SxSubcontractOrder, on_delete=models.CASCADE, related_name='material_lines',
    )
    direction = models.CharField(
        max_length=10, choices=DIRECTION_CHOICES, default=DIRECTION_OUT, db_index=True,
    )
    material_code = models.CharField(
        max_length=60, verbose_name='Mã nguyên phụ liệu / bán thành phẩm',
    )
    material_name = models.CharField(max_length=255, blank=True, default='')
    qty = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    uom_label = models.CharField(max_length=40, blank=True, default='SP')
    lot_code = models.CharField(max_length=60, blank=True, default='')
    notes = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['direction', 'pk']
        verbose_name = 'Dòng NVL/BTP GC'
        verbose_name_plural = 'Dòng NVL/BTP GC'


class SxWorkAssignment(DemoMarkedModel):
    STATUS_OPEN = 'open'
    STATUS_DONE = 'done'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_OPEN, 'Đang giao'),
        (STATUS_DONE, 'Hoàn thành'),
        (STATUS_CANCELLED, 'Hủy'),
    ]

    code = models.CharField(max_length=40, unique=True, verbose_name='Mã giao việc')
    production_order = models.ForeignKey(
        SxProductionOrder, on_delete=models.CASCADE, related_name='work_assignments',
    )
    work_center = models.ForeignKey(
        SxWorkCenter,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assignments',
        verbose_name='Tổ/chuyền',
    )
    process_name = models.CharField(max_length=120, blank=True, default='')
    title = models.CharField(max_length=200)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sx_work_assignments',
        verbose_name='Người nhận (portal)',
    )
    assignee_label = models.CharField(
        max_length=120, blank=True, default='', verbose_name='Người/tổ nhận',
    )
    work_task = models.ForeignKey(
        'tasks.WorkTask',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sx_assignments',
        verbose_name='Công việc',
    )
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN, db_index=True,
    )
    notes = models.TextField(blank=True, default='')
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Giao việc SX'
        verbose_name_plural = 'Giao việc SX'

    def __str__(self):
        return self.code


class SxDowntimeEvent(DemoMarkedModel):
    code = models.CharField(max_length=40, unique=True, verbose_name='Mã dừng')
    production_order = models.ForeignKey(
        SxProductionOrder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='downtime_events',
    )
    work_center = models.ForeignKey(
        SxWorkCenter,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='downtime_events',
    )
    team_label = models.CharField(max_length=80, blank=True, default='')
    event_date = models.DateField()
    reason = models.CharField(max_length=200, verbose_name='Lý do dừng')
    minutes = models.PositiveIntegerField(default=0, verbose_name='Số phút')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-event_date', '-pk']
        verbose_name = 'Dừng chuyền'
        verbose_name_plural = 'Dừng chuyền'

    def __str__(self):
        return self.code


class SxProductGroup(DemoMarkedModel):
    code = models.CharField(max_length=40, unique=True, verbose_name='Mã nhóm')
    name = models.CharField(max_length=120, verbose_name='Tên nhóm')
    is_active = models.BooleanField(default=True)
    notes = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        ordering = ['code']
        verbose_name = 'Nhóm sản phẩm'
        verbose_name_plural = 'Nhóm sản phẩm'

    def __str__(self):
        return f'{self.code} — {self.name}'


class SxActualCostSheet(DemoMarkedModel):
    STATUS_DRAFT = 'draft'
    STATUS_CLOSED = 'closed'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Nháp'),
        (STATUS_CLOSED, 'Đã chốt'),
    ]

    code = models.CharField(max_length=40, unique=True, verbose_name='Mã GT thực')
    production_order = models.ForeignKey(
        SxProductionOrder, on_delete=models.CASCADE, related_name='actual_cost_sheets',
    )
    period_from = models.DateField(null=True, blank=True)
    period_to = models.DateField(null=True, blank=True)
    material_cost = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0'))
    labor_cost = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0'))
    subcontract_cost = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0'))
    total_cost = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0'))
    qty_basis = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'), verbose_name='SL cơ sở (qty_done)',
    )
    unit_cost = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0'))
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True,
    )
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Giá thành thực tế'
        verbose_name_plural = 'Giá thành thực tế'

    def __str__(self):
        return self.code


class SxNcrCase(DemoMarkedModel):
    DISP_REWORK = 'rework'
    DISP_SCRAP = 'scrap'
    DISP_REMAKE = 'remake'
    DISP_USE_AS_IS = 'use_as_is'
    DISP_CHOICES = [
        (DISP_REWORK, 'Sửa hàng'),
        (DISP_SCRAP, 'Phế'),
        (DISP_REMAKE, 'Tái sản xuất'),
        (DISP_USE_AS_IS, 'Chấp nhận dùng'),
    ]
    STATUS_DRAFT = 'draft'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_DONE = 'done'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Nháp'),
        (STATUS_CONFIRMED, 'Đã xác nhận'),
        (STATUS_DONE, 'Hoàn tất'),
        (STATUS_CANCELLED, 'Hủy'),
    ]

    code = models.CharField(max_length=40, unique=True, verbose_name='Mã xử lý không đạt')
    production_order = models.ForeignKey(
        SxProductionOrder, on_delete=models.CASCADE, related_name='ncr_cases',
    )
    alert = models.ForeignKey(
        SxQcAlert, on_delete=models.SET_NULL, null=True, blank=True, related_name='ncr_cases',
    )
    disposition = models.CharField(max_length=20, choices=DISP_CHOICES, default=DISP_REWORK)
    qty = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    process_name = models.CharField(max_length=120, blank=True, default='')
    remake_order = models.ForeignKey(
        SxProductionOrder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ncr_remake_sources',
        verbose_name='Lệnh tái sản xuất',
    )
    rework_stat = models.ForeignKey(
        SxProductionStat,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ncr_reworks',
        verbose_name='Thống kê sản xuất (sửa hàng)',
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True,
    )
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Xử lý hàng không đạt'
        verbose_name_plural = 'Xử lý hàng không đạt'

    def __str__(self):
        return self.code


class SxTeamHrMap(DemoMarkedModel):
    team_label = models.CharField(max_length=80, unique=True, verbose_name='Nhãn tổ (TKSX)')
    employee_code = models.CharField(max_length=40, blank=True, default='', verbose_name='Mã NV')
    employee_name = models.CharField(max_length=120, blank=True, default='', verbose_name='Tên NV / tổ')
    notes = models.CharField(max_length=255, blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['team_label']
        verbose_name = 'Map tổ → nhân sự'
        verbose_name_plural = 'Map tổ → nhân sự'

    def __str__(self):
        return self.team_label


class SxGeneralSettings(models.Model):
    """Singleton (pk=1) — thiết lập chung module Sản xuất (cổng quy trình, QC, năng lực…)."""

    GATE_OFF = 'off'
    GATE_WARN = 'warn'
    GATE_BLOCK = 'block'
    GATE_CHOICES = [
        (GATE_OFF, 'Tắt — không kiểm tra'),
        (GATE_WARN, 'Cảnh báo — cho phép nhưng nhắc'),
        (GATE_BLOCK, 'Chặn — bắt buộc đúng bước'),
    ]

    # --- Cổng quy trình ---
    gate_release_before_issue = models.CharField(
        max_length=10, choices=GATE_CHOICES, default=GATE_BLOCK,
        verbose_name='Phát hành lệnh trước khi tạo yêu cầu xuất',
    )
    gate_issue_before_stat = models.CharField(
        max_length=10, choices=GATE_CHOICES, default=GATE_BLOCK,
        verbose_name='Xuất kho (đã ghi sổ) trước khi xác nhận thống kê',
    )
    gate_stat_before_fg = models.CharField(
        max_length=10, choices=GATE_CHOICES, default=GATE_BLOCK,
        verbose_name='Thống kê đã xác nhận trước khi nhập thành phẩm',
    )
    gate_qc_pass_before_fg = models.CharField(
        max_length=10, choices=GATE_CHOICES, default=GATE_BLOCK,
        verbose_name='Phiếu kiểm tra Đạt trước khi nhập thành phẩm',
    )
    gate_open_qc_alert_before_fg = models.CharField(
        max_length=10, choices=GATE_CHOICES, default=GATE_BLOCK,
        verbose_name='Cảnh báo chất lượng đang mở trước khi nhập thành phẩm',
    )
    gate_packing_before_done = models.CharField(
        max_length=10, choices=GATE_CHOICES, default=GATE_OFF,
        verbose_name='Đóng gói đã xác nhận trước khi hoàn thành lệnh',
    )

    # --- Chất lượng & truy xuất ---
    auto_create_qc_from_stat = models.BooleanField(
        default=True,
        verbose_name='Tự tạo yêu cầu kiểm tra khi xác nhận thống kê',
    )
    auto_create_defect_alert = models.BooleanField(
        default=True,
        verbose_name='Tự tạo cảnh báo khi tỷ lệ lỗi vượt ngưỡng',
    )
    default_defect_tolerance_pct = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal('5'),
        verbose_name='Dung sai tỷ lệ lỗi mặc định (%)',
        help_text='Dùng khi sản phẩm chưa gắn bộ tiêu chuẩn QC.',
    )
    default_sample_qty = models.PositiveIntegerField(
        default=5,
        verbose_name='Số lượng mẫu mặc định',
        help_text='Khi chưa chọn phương pháp lấy mẫu.',
    )
    trace_min_timeline_events = models.PositiveSmallIntegerField(
        default=4,
        verbose_name='Ngưỡng sự kiện timeline (Truy xuất — thiếu bước)',
        help_text='Nếu timeline ngắn hơn ngưỡng và checklist đủ, vẫn gợi ý kiểm tra chuỗi.',
    )

    # --- Năng lực & danh sách ---
    capacity_load_warn_pct = models.PositiveSmallIntegerField(
        default=80, verbose_name='Ngưỡng cảnh báo tải năng lực (%)',
    )
    capacity_load_danger_pct = models.PositiveSmallIntegerField(
        default=100, verbose_name='Ngưỡng quá tải năng lực (%)',
    )
    list_default_date_range_days = models.PositiveSmallIntegerField(
        default=7, verbose_name='Số ngày lọc danh sách mặc định',
    )

    # --- Kho & tích hợp ---
    ycx_auto_reserve_stock = models.BooleanField(
        default=True,
        verbose_name='Giữ chỗ tồn khi tạo yêu cầu xuất vật tư',
    )
    require_kv_link_for_fg_done = models.BooleanField(
        default=True,
        verbose_name='Bắt buộc liên kết phiếu nhập KiotViet để hoàn tất nhập thành phẩm',
        help_text='Tắt = gửi yêu cầu nhập thành phẩm có thể đánh dấu hoàn thành không cần KV.',
    )

    # --- Shop floor ---
    shopfloor_auto_confirm_stat = models.BooleanField(
        default=True,
        verbose_name='Shop floor: quét xong tự xác nhận thống kê',
    )
    shopfloor_default_qty_good = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('1'),
        verbose_name='Shop floor: số lượng đạt mặc định mỗi lần quét',
    )

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        verbose_name='Cập nhật bởi',
    )

    class Meta:
        verbose_name = 'Thiết lập chung sản xuất'
        verbose_name_plural = 'Thiết lập chung sản xuất'

    def __str__(self):
        return 'Thiết lập chung sản xuất'

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
