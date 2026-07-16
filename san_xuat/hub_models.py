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

    class Meta:
        ordering = ['plan_date', 'id']
        verbose_name = 'Dòng KHCT'
        verbose_name_plural = 'Dòng KHCT'


class SxMaterialPlan(DemoMarkedModel):
    code = models.CharField(max_length=40, unique=True, verbose_name='Mã KHNVL')
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

    class Meta:
        ordering = ['id']
        verbose_name = 'Dòng KHNVL'
        verbose_name_plural = 'Dòng KHNVL'


class SxNplPurchaseRequest(DemoMarkedModel):
    code = models.CharField(max_length=40, unique=True, verbose_name='Mã YCM')
    material_plan = models.ForeignKey(
        SxMaterialPlan, on_delete=models.SET_NULL, null=True, blank=True, related_name='purchase_requests',
    )
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, default='draft')
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
    code = models.CharField(max_length=40, unique=True, verbose_name='Mã DMH')
    supplier_name = models.CharField(max_length=200, blank=True, default='')
    purchase_request = models.ForeignKey(
        SxNplPurchaseRequest, on_delete=models.SET_NULL, null=True, blank=True, related_name='purchase_orders',
    )
    status = models.CharField(max_length=20, default='draft')
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

    code = models.CharField(max_length=40, unique=True, verbose_name='Mã LSX')
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
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-order_date', 'code']
        verbose_name = 'Lệnh sản xuất'
        verbose_name_plural = 'Lệnh sản xuất'

    def __str__(self):
        return self.code


class SxDisassemblyOrder(DemoMarkedModel):
    code = models.CharField(max_length=40, unique=True, verbose_name='Mã LTD')
    product_code = models.CharField(max_length=60, db_index=True)
    product_name = models.CharField(max_length=255, blank=True, default='')
    qty = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    order_date = models.DateField()
    status = models.CharField(max_length=20, default='draft')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-order_date']
        verbose_name = 'Lệnh tháo dỡ'
        verbose_name_plural = 'Lệnh tháo dỡ'

    def __str__(self):
        return self.code


class SxMaterialIssueRequest(DemoMarkedModel):
    code = models.CharField(max_length=40, unique=True, verbose_name='Mã YCX')
    production_order = models.ForeignKey(
        SxProductionOrder, on_delete=models.CASCADE, related_name='material_issue_requests',
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

    class Meta:
        ordering = ['id']


class SxProductionStat(DemoMarkedModel):
    code = models.CharField(max_length=40, unique=True, verbose_name='Mã TKSX')
    production_order = models.ForeignKey(
        SxProductionOrder, on_delete=models.CASCADE, related_name='production_stats',
    )
    stat_date = models.DateField()
    process_name = models.CharField(max_length=120, blank=True, default='')
    qty_good = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    qty_defect = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    team_label = models.CharField(max_length=80, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-stat_date']
        verbose_name = 'Thống kê sản xuất'
        verbose_name_plural = 'Thống kê sản xuất'

    def __str__(self):
        return self.code


class SxFgReceiptRequest(DemoMarkedModel):
    code = models.CharField(max_length=40, unique=True, verbose_name='Mã YCNTP')
    production_order = models.ForeignKey(
        SxProductionOrder, on_delete=models.CASCADE, related_name='fg_receipt_requests',
    )
    request_date = models.DateField()
    qty = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    status = models.CharField(max_length=20, default='draft')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-request_date']
        verbose_name = 'Yêu cầu nhập TP'
        verbose_name_plural = 'Yêu cầu nhập TP'

    def __str__(self):
        return self.code


class SxNplSurplus(DemoMarkedModel):
    code = models.CharField(max_length=40, unique=True, verbose_name='Mã NPL thừa')
    production_order = models.ForeignKey(
        SxProductionOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name='npl_surplus_records',
    )
    material_code = models.CharField(max_length=60)
    material_name = models.CharField(max_length=255, blank=True, default='')
    qty = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0'))
    recorded_at = models.DateField()
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
        verbose_name = 'Bàn giao BTP'
        verbose_name_plural = 'Bàn giao BTP'

    def __str__(self):
        return self.code


class SxWipReturn(DemoMarkedModel):
    code = models.CharField(max_length=40, unique=True, verbose_name='Mã trả BTP')
    handover = models.ForeignKey(
        SxWipHandover, on_delete=models.SET_NULL, null=True, blank=True, related_name='returns',
    )
    production_order = models.ForeignKey(
        SxProductionOrder, on_delete=models.CASCADE, related_name='wip_returns',
    )
    qty = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    return_date = models.DateField()
    reason = models.CharField(max_length=255, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-return_date']
        verbose_name = 'Trả lại BTP'
        verbose_name_plural = 'Trả lại BTP'

    def __str__(self):
        return self.code


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
    product_code = models.CharField(max_length=60, db_index=True)
    product_name = models.CharField(max_length=255, blank=True, default='')
    stage_name = models.CharField(max_length=120, blank=True, default='')
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


# --- Giá thành kế hoạch ---


class SxStandardCostSheet(DemoMarkedModel):
    code = models.CharField(max_length=40, unique=True, verbose_name='Mã GTDM')
    name = models.CharField(max_length=200)
    date_from = models.DateField()
    date_to = models.DateField()
    status = models.CharField(max_length=20, default='confirmed')
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
    code = models.CharField(max_length=40, unique=True, verbose_name='Mã GTĐH')
    name = models.CharField(max_length=200)
    kv_order_code = models.CharField(max_length=80, blank=True, default='', verbose_name='Mã đơn KV')
    date_from = models.DateField()
    date_to = models.DateField()
    total_cost = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0'))
    status = models.CharField(max_length=20, default='confirmed')
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
    line_cost = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0'))

    class Meta:
        ordering = ['id']
