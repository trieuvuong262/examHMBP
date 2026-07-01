from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from kho_npl.choices import (
    ADJUST_STATUS_LABELS,
    ADJUST_STATUS_PENDING,
    DISPOSAL_REASON_CHOICES,
    DISPOSAL_REASON_DAMAGED,
    DOC_STATUS_DRAFT,
    DOC_STATUS_LABELS,
    ISSUE_STATUS_LABELS,
    RECEIPT_STATUS_LABELS,
    STOCKTAKE_STATUS_DRAFT,
    STOCKTAKE_STATUS_LABELS,
    TRANSFER_STATUS_DRAFT,
    TRANSFER_STATUS_LABELS,
)


class MaterialCategory(models.Model):
    code = models.SlugField(max_length=40, unique=True, verbose_name='Mã nhóm')
    name = models.CharField(max_length=120, verbose_name='Tên nhóm')
    parent = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='children',
        verbose_name='Nhóm cấp 1',
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Thứ tự')
    is_active = models.BooleanField(default=True, verbose_name='Đang dùng')

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'Nhóm nguyên phụ liệu'
        verbose_name_plural = 'Nhóm nguyên phụ liệu'

    def __str__(self):
        return self.name

    @property
    def parent_name(self):
        return self.parent.name if self.parent_id else '—'

    @property
    def is_root(self):
        return self.parent_id is None

    @property
    def is_leaf(self):
        return self.parent_id is not None


class Unit(models.Model):
    code = models.SlugField(max_length=20, unique=True, verbose_name='Mã ĐVT')
    name = models.CharField(max_length=40, verbose_name='Tên ĐVT')
    is_active = models.BooleanField(default=True, verbose_name='Đang dùng')

    class Meta:
        ordering = ['name']
        verbose_name = 'Đơn vị tính'
        verbose_name_plural = 'Đơn vị tính'

    def __str__(self):
        return self.name


class MaterialColor(models.Model):
    code = models.SlugField(max_length=40, unique=True, verbose_name='Mã màu')
    name = models.CharField(max_length=80, verbose_name='Tên màu')
    hex_code = models.CharField(max_length=7, verbose_name='Mã hex')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Thứ tự')
    is_active = models.BooleanField(default=True, verbose_name='Đang dùng')

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'Màu sắc NPL'
        verbose_name_plural = 'Màu sắc NPL'

    def __str__(self):
        return self.name


class MaterialSpecification(models.Model):
    code = models.SlugField(max_length=40, unique=True, verbose_name='Mã quy cách')
    name = models.CharField(max_length=120, verbose_name='Quy cách / khổ')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Thứ tự')
    is_active = models.BooleanField(default=True, verbose_name='Đang dùng')

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'Quy cách NPL'
        verbose_name_plural = 'Quy cách NPL'

    def __str__(self):
        return self.name


class WarehouseLocation(models.Model):
    code = models.CharField(max_length=40, unique=True, verbose_name='Mã vị trí')
    name = models.CharField(max_length=120, verbose_name='Tên vị trí / kệ')
    is_active = models.BooleanField(default=True, verbose_name='Đang dùng')

    class Meta:
        ordering = ['code']
        verbose_name = 'Vị trí kho'
        verbose_name_plural = 'Vị trí kho'

    def display_label(self) -> str:
        """Tên hiển thị ngoài Thiết lập — không kèm mã."""
        name = (self.name or '').strip()
        return name or self.code

    def __str__(self):
        return self.display_label()


class Supplier(models.Model):
    code = models.CharField(max_length=40, unique=True, verbose_name='Mã NCC')
    name = models.CharField(max_length=200, verbose_name='Tên nhà cung cấp')
    phone = models.CharField(max_length=40, blank=True, verbose_name='Điện thoại')
    notes = models.TextField(blank=True, verbose_name='Ghi chú')
    is_active = models.BooleanField(default=True, verbose_name='Đang dùng')

    class Meta:
        ordering = ['name']
        verbose_name = 'Nhà cung cấp'
        verbose_name_plural = 'Nhà cung cấp'

    def __str__(self):
        return self.name


class Material(models.Model):
    code = models.CharField(max_length=60, unique=True, verbose_name='Mã NPL')
    name = models.CharField(max_length=200, verbose_name='Tên nguyên phụ liệu')
    category = models.ForeignKey(
        MaterialCategory,
        on_delete=models.PROTECT,
        related_name='materials',
        verbose_name='Nhóm',
    )
    color = models.ForeignKey(
        MaterialColor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='materials',
        verbose_name='Màu sắc',
    )
    specification = models.ForeignKey(
        MaterialSpecification,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='materials',
        verbose_name='Quy cách / khổ',
    )
    unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name='materials',
        verbose_name='Đơn vị tính',
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='materials',
        verbose_name='NCC chính',
    )
    min_stock = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Tồn tối thiểu',
    )
    image = models.ImageField(upload_to='npl/materials/', blank=True, verbose_name='Hình ảnh')
    notes = models.TextField(blank=True, verbose_name='Ghi chú')
    is_active = models.BooleanField(default=True, verbose_name='Đang dùng')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['code']
        verbose_name = 'Nguyên phụ liệu'
        verbose_name_plural = 'Nguyên phụ liệu'

    def __str__(self):
        return f'{self.code} — {self.name}'


class StockBalance(models.Model):
    material = models.ForeignKey(
        Material,
        on_delete=models.CASCADE,
        related_name='balances',
        verbose_name='Nguyên phụ liệu',
    )
    location = models.ForeignKey(
        WarehouseLocation,
        on_delete=models.PROTECT,
        related_name='balances',
        verbose_name='Vị trí',
    )
    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Số lượng',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('material', 'location')]
        verbose_name = 'Tồn theo vị trí'
        verbose_name_plural = 'Tồn theo vị trí'

    def __str__(self):
        return f'{self.material.code} @ {self.location.code}: {self.quantity}'


class StockReceipt(models.Model):
    number = models.CharField(max_length=30, unique=True, verbose_name='Mã phiếu nhập')
    receipt_date = models.DateField(verbose_name='Ngày nhập')
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='receipts',
        verbose_name='Nhà cung cấp',
    )
    po_number = models.CharField(max_length=60, blank=True, verbose_name='Số PO / đơn mua')
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='npl_receipts_received',
        verbose_name='Người nhập',
    )
    checked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='npl_receipts_checked',
        verbose_name='Người kiểm',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='npl_receipts_created',
        verbose_name='Người tạo',
    )
    notes = models.TextField(blank=True, verbose_name='Ghi chú')
    attachment = models.FileField(
        upload_to='npl/receipts/attachments/',
        blank=True,
        verbose_name='Chứng từ / ảnh',
    )
    status = models.CharField(
        max_length=20,
        choices=[(k, v) for k, v in RECEIPT_STATUS_LABELS.items()],
        default=DOC_STATUS_DRAFT,
        verbose_name='Trạng thái',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-receipt_date', '-id']
        verbose_name = 'Phiếu nhập kho'
        verbose_name_plural = 'Phiếu nhập kho'

    def __str__(self):
        return self.number


class StockReceiptLine(models.Model):
    receipt = models.ForeignKey(
        StockReceipt,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name='Phiếu nhập',
    )
    material = models.ForeignKey(
        Material,
        on_delete=models.PROTECT,
        related_name='receipt_lines',
        verbose_name='Nguyên phụ liệu',
    )
    ordered_qty = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='SL đặt',
    )
    received_qty = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='SL nhập',
    )
    location = models.ForeignKey(
        WarehouseLocation,
        on_delete=models.PROTECT,
        related_name='receipt_lines',
        verbose_name='Vị trí kho',
    )
    notes = models.CharField(max_length=255, blank=True, verbose_name='Ghi chú')

    class Meta:
        verbose_name = 'Chi tiết phiếu nhập'
        verbose_name_plural = 'Chi tiết phiếu nhập'


class StockIssue(models.Model):
    number = models.CharField(max_length=30, unique=True, verbose_name='Mã phiếu xuất')
    issue_date = models.DateField(verbose_name='Ngày xuất')
    issue_type = models.CharField(
        max_length=120,
        blank=True,
        default='',
        verbose_name='Lý do xuất',
    )
    production_order = models.CharField(max_length=60, blank=True, verbose_name='Lệnh sản xuất')
    product_code = models.CharField(max_length=60, blank=True, verbose_name='Mã sản phẩm')
    recipient_department = models.CharField(max_length=120, blank=True, verbose_name='Bộ phận nhận')
    recipient_name = models.CharField(max_length=120, blank=True, verbose_name='Người nhận')
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='npl_issues_received',
        verbose_name='Người nhận',
    )
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='npl_issues_issued',
        verbose_name='Người xuất',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='npl_issues_created',
        verbose_name='Người tạo',
    )
    notes = models.TextField(blank=True, verbose_name='Ghi chú')
    attachment = models.FileField(
        upload_to='npl/issues/attachments/',
        blank=True,
        verbose_name='Chứng từ / ảnh',
    )
    status = models.CharField(
        max_length=20,
        choices=[(k, v) for k, v in ISSUE_STATUS_LABELS.items()],
        default=DOC_STATUS_DRAFT,
        verbose_name='Trạng thái',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-issue_date', '-id']
        verbose_name = 'Phiếu xuất kho'
        verbose_name_plural = 'Phiếu xuất kho'

    def __str__(self):
        return self.number


class StockIssueLine(models.Model):
    issue = models.ForeignKey(
        StockIssue,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name='Phiếu xuất',
    )
    material = models.ForeignKey(
        Material,
        on_delete=models.PROTECT,
        related_name='issue_lines',
        verbose_name='Nguyên phụ liệu',
    )
    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        verbose_name='Số lượng',
    )
    location = models.ForeignKey(
        WarehouseLocation,
        on_delete=models.PROTECT,
        related_name='issue_lines',
        verbose_name='Vị trí kho',
    )
    notes = models.CharField(max_length=255, blank=True, verbose_name='Ghi chú')

    class Meta:
        verbose_name = 'Chi tiết phiếu xuất'
        verbose_name_plural = 'Chi tiết phiếu xuất'


class StockDisposal(models.Model):
    number = models.CharField(max_length=30, unique=True, verbose_name='Mã phiếu hủy')
    disposal_date = models.DateField(verbose_name='Ngày hủy')
    from_location = models.ForeignKey(
        WarehouseLocation,
        on_delete=models.PROTECT,
        related_name='disposals_out',
        verbose_name='Kho nguồn',
    )
    reason = models.CharField(
        max_length=30,
        choices=DISPOSAL_REASON_CHOICES,
        default=DISPOSAL_REASON_DAMAGED,
        verbose_name='Lý do hủy',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='npl_disposals_created',
        verbose_name='Người tạo',
    )
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='npl_disposals_posted',
        verbose_name='Người ghi sổ',
    )
    notes = models.TextField(blank=True, verbose_name='Ghi chú')
    attachment = models.FileField(
        upload_to='npl/disposals/attachments/',
        blank=True,
        verbose_name='Chứng từ / ảnh',
    )
    status = models.CharField(
        max_length=20,
        choices=[(k, v) for k, v in DOC_STATUS_LABELS.items()],
        default=DOC_STATUS_DRAFT,
        verbose_name='Trạng thái',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-disposal_date', '-id']
        verbose_name = 'Phiếu hủy'
        verbose_name_plural = 'Phiếu hủy'

    def __str__(self):
        return self.number


class StockDisposalLine(models.Model):
    disposal = models.ForeignKey(
        StockDisposal,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name='Phiếu hủy',
    )
    material = models.ForeignKey(
        Material,
        on_delete=models.PROTECT,
        related_name='disposal_lines',
        verbose_name='Nguyên phụ liệu',
    )
    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        verbose_name='Số lượng',
    )
    notes = models.CharField(max_length=255, blank=True, verbose_name='Ghi chú')

    class Meta:
        verbose_name = 'Chi tiết phiếu hủy'
        verbose_name_plural = 'Chi tiết phiếu hủy'


class StockTransfer(models.Model):
    number = models.CharField(max_length=30, unique=True, verbose_name='Mã phiếu chuyển')
    transfer_date = models.DateField(verbose_name='Ngày chuyển')
    from_location = models.ForeignKey(
        WarehouseLocation,
        on_delete=models.PROTECT,
        related_name='transfers_out',
        verbose_name='Kho gửi',
    )
    to_location = models.ForeignKey(
        WarehouseLocation,
        on_delete=models.PROTECT,
        related_name='transfers_in',
        verbose_name='Kho nhận',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='npl_transfers_created',
        verbose_name='Người tạo',
    )
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='npl_transfers_sent',
        verbose_name='Người gửi',
    )
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='npl_transfers_received',
        verbose_name='Người nhận',
    )
    notes = models.TextField(blank=True, verbose_name='Ghi chú')
    attachment = models.FileField(
        upload_to='npl/transfers/attachments/',
        blank=True,
        verbose_name='Chứng từ / ảnh',
    )
    status = models.CharField(
        max_length=20,
        choices=[(k, v) for k, v in TRANSFER_STATUS_LABELS.items()],
        default=TRANSFER_STATUS_DRAFT,
        verbose_name='Trạng thái',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-transfer_date', '-id']
        verbose_name = 'Phiếu chuyển kho'
        verbose_name_plural = 'Phiếu chuyển kho'

    def __str__(self):
        return self.number


class StockTransferLine(models.Model):
    transfer = models.ForeignKey(
        StockTransfer,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name='Phiếu chuyển',
    )
    material = models.ForeignKey(
        Material,
        on_delete=models.PROTECT,
        related_name='transfer_lines',
        verbose_name='Nguyên phụ liệu',
    )
    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        verbose_name='Số lượng',
    )
    notes = models.CharField(max_length=255, blank=True, verbose_name='Ghi chú')

    class Meta:
        verbose_name = 'Chi tiết phiếu chuyển'
        verbose_name_plural = 'Chi tiết phiếu chuyển'


class StockAdjustment(models.Model):
    number = models.CharField(max_length=30, unique=True, verbose_name='Mã phiếu điều chỉnh')
    adjust_date = models.DateField(verbose_name='Ngày điều chỉnh')
    reason = models.TextField(verbose_name='Lý do')
    attachment = models.FileField(
        upload_to='npl/adjustments/attachments/',
        blank=True,
        verbose_name='Chứng từ / ảnh',
    )
    proposed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='npl_adjustments_proposed',
        verbose_name='Người đề xuất',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='npl_adjustments_approved',
        verbose_name='Người duyệt',
    )
    status = models.CharField(
        max_length=20,
        choices=[(k, v) for k, v in ADJUST_STATUS_LABELS.items()],
        default=ADJUST_STATUS_PENDING,
        verbose_name='Trạng thái',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-adjust_date', '-id']
        verbose_name = 'Phiếu điều chỉnh'
        verbose_name_plural = 'Phiếu điều chỉnh'

    def __str__(self):
        return self.number


class StockAdjustmentLine(models.Model):
    adjustment = models.ForeignKey(
        StockAdjustment,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name='Phiếu điều chỉnh',
    )
    material = models.ForeignKey(
        Material,
        on_delete=models.PROTECT,
        related_name='adjustment_lines',
        verbose_name='Nguyên phụ liệu',
    )
    location = models.ForeignKey(
        WarehouseLocation,
        on_delete=models.PROTECT,
        related_name='adjustment_lines',
        verbose_name='Vị trí',
    )
    system_qty = models.DecimalField(max_digits=14, decimal_places=3, verbose_name='Tồn hệ thống')
    actual_qty = models.DecimalField(max_digits=14, decimal_places=3, verbose_name='Tồn thực tế')
    notes = models.CharField(max_length=255, blank=True, verbose_name='Ghi chú')

    class Meta:
        verbose_name = 'Dòng điều chỉnh'
        verbose_name_plural = 'Dòng điều chỉnh'
        constraints = [
            models.UniqueConstraint(
                fields=['adjustment', 'material', 'location'],
                name='uniq_adjustment_material_location',
            ),
        ]

    @property
    def variance(self):
        return self.actual_qty - self.system_qty

    def __str__(self):
        return f'{self.material.code} @ {self.location.code}'


class Stocktake(models.Model):
    number = models.CharField(max_length=30, unique=True, verbose_name='Mã kỳ kiểm kê')
    name = models.CharField(max_length=200, verbose_name='Tên kỳ')
    stocktake_date = models.DateField(verbose_name='Ngày kiểm kê')
    location = models.ForeignKey(
        WarehouseLocation,
        on_delete=models.PROTECT,
        related_name='stocktakes',
        verbose_name='Kho kiểm kê',
    )
    status = models.CharField(
        max_length=20,
        choices=[(k, v) for k, v in STOCKTAKE_STATUS_LABELS.items()],
        default=STOCKTAKE_STATUS_DRAFT,
        verbose_name='Trạng thái',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='npl_stocktakes_created',
        verbose_name='Người tạo',
    )
    notes = models.TextField(blank=True, verbose_name='Ghi chú')
    attachment = models.FileField(
        upload_to='npl/stocktakes/attachments/',
        blank=True,
        verbose_name='Chứng từ / ảnh',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-stocktake_date', '-id']
        verbose_name = 'Kỳ kiểm kê'
        verbose_name_plural = 'Kỳ kiểm kê'

    def __str__(self):
        return f'{self.number} — {self.name}'


class StocktakeLine(models.Model):
    stocktake = models.ForeignKey(
        Stocktake,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name='Kỳ kiểm kê',
    )
    material = models.ForeignKey(
        Material,
        on_delete=models.PROTECT,
        related_name='stocktake_lines',
        verbose_name='Nguyên phụ liệu',
    )
    location = models.ForeignKey(
        WarehouseLocation,
        on_delete=models.PROTECT,
        related_name='stocktake_lines',
        verbose_name='Vị trí',
    )
    system_qty = models.DecimalField(max_digits=14, decimal_places=3, verbose_name='Tồn hệ thống')
    actual_qty = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name='Tồn thực tế',
    )
    notes = models.CharField(max_length=255, blank=True, verbose_name='Ghi chú')

    class Meta:
        verbose_name = 'Dòng kiểm kê'
        verbose_name_plural = 'Dòng kiểm kê'

    @property
    def variance(self):
        if self.actual_qty is None:
            return None
        return self.actual_qty - self.system_qty


class StockLedger(models.Model):
    REF_RECEIPT = 'receipt'
    REF_ISSUE = 'issue'
    REF_ADJUSTMENT = 'adjustment'
    REF_STOCKTAKE = 'stocktake'
    REF_TRANSFER = 'transfer'
    REF_DISPOSAL = 'disposal'

    material = models.ForeignKey(
        Material,
        on_delete=models.CASCADE,
        related_name='ledger_entries',
        verbose_name='Nguyên phụ liệu',
    )
    location = models.ForeignKey(
        WarehouseLocation,
        on_delete=models.PROTECT,
        related_name='ledger_entries',
        verbose_name='Vị trí',
    )
    qty_delta = models.DecimalField(max_digits=14, decimal_places=3, verbose_name='Biến động')
    balance_after = models.DecimalField(max_digits=14, decimal_places=3, verbose_name='Tồn sau')
    ref_type = models.CharField(max_length=20, verbose_name='Loại chứng từ')
    ref_id = models.PositiveIntegerField(verbose_name='ID chứng từ')
    ref_number = models.CharField(max_length=30, blank=True, verbose_name='Số chứng từ')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='npl_ledger_entries',
        verbose_name='Người thực hiện',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'Sổ kho'
        verbose_name_plural = 'Sổ kho'
