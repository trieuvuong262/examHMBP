import json
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse

from san_xuat.design_nas_storage import (
    DesignDocNasStorage,
    design_file_upload_to,
    is_legacy_design_path,
)


class ProductTechDoc(models.Model):
    """Hồ sơ tài liệu sản xuất neo theo mã SX gốc trong kho sản phẩm."""

    product_code = models.CharField(
        max_length=60,
        unique=True,
        db_index=True,
        verbose_name='Mã sản phẩm',
    )
    product_name = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='Tên sản phẩm (snapshot)',
    )
    product_image_url = models.URLField(
        max_length=500,
        blank=True,
        default='',
        verbose_name='Ảnh sản phẩm',
    )
    kv_product_id = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name='KiotViet product id',
    )
    notes = models.TextField(blank=True, default='', verbose_name='Ghi chú')
    description = models.TextField(
        blank=True,
        default='',
        verbose_name='Mô tả chi tiết',
        help_text='Mô tả kỹ thuật, yêu cầu sản xuất, lưu ý…',
    )
    season = models.CharField(
        max_length=80,
        blank=True,
        default='',
        verbose_name='Mùa / BST',
    )
    main_material = models.CharField(
        max_length=120,
        blank=True,
        default='',
        verbose_name='Chất liệu chính',
    )
    is_active = models.BooleanField(default=True, verbose_name='Đang dùng')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='san_xuat_tech_docs',
        verbose_name='Người tạo',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['product_code']
        verbose_name = 'Hồ sơ tài liệu SX'
        verbose_name_plural = 'Hồ sơ tài liệu SX'

    def __str__(self):
        name = self.product_name or ''
        return f'{self.product_code} — {name}'.strip(' —')

    @property
    def display_image_url(self) -> str:
        cached = getattr(self, '_display_image_url', None)
        if cached is not None:
            return cached
        urls = getattr(self, '_display_image_urls', None)
        if urls:
            return urls[0]
        return (self.product_image_url or '').strip()

    @property
    def display_image_urls(self) -> list[str]:
        cached = getattr(self, '_display_image_urls', None)
        if cached is not None:
            return list(cached)
        url = self.display_image_url
        return [url] if url else []

    @property
    def display_image_urls_json(self) -> str:
        return json.dumps(self.display_image_urls, ensure_ascii=False)


class TechDocDesignFile(models.Model):
    """Tài liệu thiết kế đính kèm hồ sơ SX (PDF, ảnh, CAD...)."""

    PURPOSE_DESIGN = 'design'
    PURPOSE_GALLERY = 'gallery'
    PURPOSE_CHOICES = [
        (PURPOSE_DESIGN, 'Rập / tài liệu'),
        (PURPOSE_GALLERY, 'Ảnh mô tả'),
    ]

    tech_doc = models.ForeignKey(
        ProductTechDoc,
        on_delete=models.CASCADE,
        related_name='design_files',
        verbose_name='Hồ sơ SX',
    )
    file = models.FileField(
        upload_to=design_file_upload_to,
        storage=DesignDocNasStorage(),
        max_length=500,
        verbose_name='Tệp',
    )
    title = models.CharField(
        max_length=200,
        blank=True,
        default='',
        verbose_name='Tiêu đề',
        help_text='Để trống = dùng tên file.',
    )
    notes = models.CharField(max_length=255, blank=True, default='', verbose_name='Ghi chú')
    purpose = models.CharField(
        max_length=20,
        choices=PURPOSE_CHOICES,
        default=PURPOSE_DESIGN,
        db_index=True,
        verbose_name='Loại',
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Thứ tự')
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='san_xuat_design_uploads',
        verbose_name='Người tải lên',
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at', '-pk']
        verbose_name = 'Tài liệu thiết kế'
        verbose_name_plural = 'Tài liệu thiết kế'

    def __str__(self):
        return self.display_name

    @property
    def display_name(self) -> str:
        if self.title.strip():
            return self.title.strip()
        name = (self.file.name or '').rsplit('/', 1)[-1]
        return name or f'Tài liệu #{self.pk}'

    @property
    def file_url(self) -> str:
        if not self.file or not self.file.name:
            return ''
        if is_legacy_design_path(self.file.name):
            return self.file.url
        if not self.pk:
            return ''
        return reverse('san_xuat:design_file', kwargs={'pk': self.pk})

    @property
    def is_image(self) -> bool:
        name = (self.file.name or '').lower()
        return name.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'))

    @property
    def is_pdf(self) -> bool:
        return (self.file.name or '').lower().endswith('.pdf')

    @property
    def file_ext(self) -> str:
        name = (self.file.name or '').rsplit('/', 1)[-1].lower()
        if '.' not in name:
            return ''
        return '.' + name.rsplit('.', 1)[-1]

    @property
    def is_office(self) -> bool:
        return self.file_ext in {
            '.doc', '.docx', '.odt', '.rtf',
            '.xls', '.xlsx', '.ods', '.csv',
        }

    @property
    def is_ai(self) -> bool:
        return self.file_ext == '.ai'

    @property
    def preview_kind(self) -> str:
        if self.is_image:
            return 'image'
        if self.is_pdf:
            return 'pdf'
        if self.is_office:
            return 'office'
        if self.is_ai:
            return 'ai'
        return 'file'


class BomVersion(models.Model):
    STATUS_DRAFT = 'draft'
    STATUS_ACTIVE = 'active'
    STATUS_ARCHIVED = 'archived'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Sẵn sàng'),
        (STATUS_ACTIVE, 'Sẵn sàng'),
        (STATUS_ARCHIVED, 'Sẵn sàng'),
    ]

    tech_doc = models.ForeignKey(
        ProductTechDoc,
        on_delete=models.CASCADE,
        related_name='bom_versions',
        verbose_name='Hồ sơ SX',
    )
    version_label = models.CharField(
        max_length=40,
        default='v1',
        verbose_name='Phiên bản',
        help_text='Tên bản BOM ngang hàng, vd. v1, Nội bộ, Gia công.',
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_index=True,
        verbose_name='Trạng thái',
    )
    overhead_pct = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Phụ phí (%)',
        help_text='Phần trăm cộng thêm trên (NVL + nhân công).',
    )
    overhead_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Chi phí sản xuất chung',
        help_text='Số tiền cố định / 1 SP — KHSH nhập tay.',
    )
    notes = models.TextField(blank=True, default='', verbose_name='Ghi chú')
    routing = models.ForeignKey(
        'san_xuat.SxRouting',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bom_versions',
        verbose_name='Routing mã hàng',
        help_text='Quy trình công đoạn IE gắn với BOM này.',
    )
    activated_at = models.DateTimeField(null=True, blank=True, verbose_name='Ngày kích hoạt')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='san_xuat_bom_versions',
        verbose_name='Người tạo',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Phiên bản BOM'
        verbose_name_plural = 'Phiên bản BOM'
        constraints = [
            models.UniqueConstraint(
                fields=['tech_doc', 'version_label'],
                name='san_xuat_bom_unique_label_per_doc',
            ),
        ]

    def __str__(self):
        return f'{self.tech_doc.product_code} / {self.version_label} ({self.status})'


class BomLine(models.Model):
    bom = models.ForeignKey(
        BomVersion,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name='BOM',
    )
    material = models.ForeignKey(
        'kho_npl.Material',
        on_delete=models.PROTECT,
        related_name='san_xuat_bom_lines',
        verbose_name='Nguyên phụ liệu',
    )
    substitute_material = models.ForeignKey(
        'kho_npl.Material',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='san_xuat_bom_substitutes',
        verbose_name='NVL thay thế',
        help_text='Khi tồn NVL chính thiếu, YCX có thể dùng mã này.',
    )
    qty = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Định mức',
    )
    scrap_pct = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Hao hụt (%)',
    )
    size_code = models.CharField(
        max_length=20,
        blank=True,
        default='',
        verbose_name='Size',
        help_text='Để trống = áp dụng mọi size.',
    )
    notes = models.CharField(max_length=255, blank=True, default='', verbose_name='Ghi chú')
    sort_order = models.PositiveSmallIntegerField(default=0, verbose_name='Thứ tự')

    class Meta:
        ordering = ['sort_order', 'id']
        verbose_name = 'Dòng BOM'
        verbose_name_plural = 'Dòng BOM'

    def __str__(self):
        return f'{self.material.code} × {self.qty}'

    @property
    def qty_with_scrap(self) -> Decimal:
        factor = Decimal('1') + (self.scrap_pct or Decimal('0')) / Decimal('100')
        return (self.qty * factor).quantize(Decimal('0.0001'))

    def resolve_issue_material(self, *, needed_qty: Decimal | None = None):
        """Chọn NVL xuất: ưu tiên mã chính; nếu tồn khả dụng thiếu và có NVL thay thế thì dùng thay thế."""
        from kho_npl.services.reservation import material_available_qty

        primary = self.material
        if not self.substitute_material_id:
            return primary
        need = needed_qty if needed_qty is not None else Decimal('0')
        if material_available_qty(primary) >= need:
            return primary
        return self.substitute_material


class SxProcessName(models.Model):
    """Danh mục công đoạn dùng chung (hồ sơ BOM, lệnh SX, thống kê)."""

    name = models.CharField(max_length=120, unique=True, verbose_name='Tên công đoạn')
    sort_order = models.PositiveSmallIntegerField(default=100, db_index=True, verbose_name='Thứ tự')
    is_active = models.BooleanField(default=True, db_index=True, verbose_name='Đang dùng')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'Danh mục công đoạn'
        verbose_name_plural = 'Danh mục công đoạn'

    def __str__(self):
        return self.name


class ProcessStep(models.Model):
    bom = models.ForeignKey(
        BomVersion,
        on_delete=models.CASCADE,
        related_name='process_steps',
        verbose_name='BOM',
    )
    sequence = models.PositiveSmallIntegerField(default=10, verbose_name='Thứ tự')
    process_name = models.CharField(max_length=120, verbose_name='Tên công đoạn')
    operation = models.ForeignKey(
        'san_xuat.SxOperation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bom_process_steps',
        verbose_name='Công đoạn chuẩn (IE)',
    )
    op_code = models.CharField(max_length=30, blank=True, default='', db_index=True, verbose_name='Mã công đoạn')
    routing_line = models.ForeignKey(
        'san_xuat.SxRoutingLine',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bom_process_steps',
        verbose_name='Dòng routing',
    )
    norm_per_hour = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name='Định mức (cái/giờ)',
    )
    cost_per_hour = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Chi phí giờ (VNĐ)',
    )
    piece_rate = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Đơn giá SP (VNĐ/cái)',
        help_text='Lương sản phẩm = SL đạt TKSX × đơn giá.',
    )
    std_time_minutes = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Chuẩn giờ (phút/cái)',
        help_text='Thời gian chuẩn một sản phẩm ở công đoạn này.',
    )
    work_center = models.ForeignKey(
        'san_xuat.SxWorkCenter',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='process_steps',
        verbose_name='Bộ phận chịu trách nhiệm',
        help_text='Bộ phận / tổ thuộc phòng Sản xuất phụ trách công đoạn này.',
    )
    notes = models.CharField(max_length=255, blank=True, default='', verbose_name='Ghi chú')

    class Meta:
        ordering = ['sequence', 'id']
        verbose_name = 'Công đoạn'
        verbose_name_plural = 'Công đoạn'

    def __str__(self):
        return f'{self.sequence}. {self.process_name}'


class CostingSnapshot(models.Model):
    """Bản chốt costing tại một thời điểm."""

    bom = models.ForeignKey(
        BomVersion,
        on_delete=models.CASCADE,
        related_name='costing_snapshots',
        verbose_name='BOM',
    )
    material_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    labor_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    overhead_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    total_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    sell_price = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    margin = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='san_xuat_costing_snapshots',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Bản chốt costing'
        verbose_name_plural = 'Bản chốt costing'

    def __str__(self):
        return f'Costing {self.bom} @ {self.created_at:%Y-%m-%d}'


# Hub: kế hoạch / điều phối / QC / giá thành KH (import để Django register models)
from san_xuat.hub_models import (  # noqa: E402,F401
    SxActualCostSheet,
    SxColor,
    SxCostType,
    SxDetailPlan,
    SxDetailPlanLine,
    SxDisassemblyOrder,
    SxDisassemblyOrderLine,
    SxDowntimeEvent,
    SxFgReceiptLine,
    SxFgReceiptRequest,
    SxHoliday,
    SxMaterialIssueRequest,
    SxMaterialIssueRequestLine,
    SxMaterialPlan,
    SxMaterialPlanLine,
    SxNcrCase,
    SxNplPurchaseRequest,
    SxNplPurchaseRequestLine,
    SxNplSurplus,
    SxOrderPlanCost,
    SxOrderPlanCostLine,
    SxOrderPlanCostLineExtra,
    SxOverallPlan,
    SxOverallPlanLine,
    SxPackingLine,
    SxPackingRecord,
    SxPlanAuditLog,
    SxProductGroup,
    SxProductionOrder,
    SxProductionOrderLine,
    SxProductStockPolicy,
    SxProductionStat,
    SxPurchaseOrder,
    SxPurchaseOrderLine,
    SxSalesOrder,
    SxSalesOrderLine,
    SxSalesOrderRoutingLine,
    SxQcAlert,
    SxQcCriteria,
    SxQcCriteriaGroup,
    SxQcDefect,
    SxQcDefectGroup,
    SxQcInspection,
    SxQcInspectionCriteriaLine,
    SxQcInspectionDefectLine,
    SxQcRequest,
    SxQcSamplingMethod,
    SxQcStandardCriteria,
    SxQcStandardSet,
    SxSize,
    SxSku,
    SxStandardCostLine,
    SxStandardCostSheet,
    SxSubcontractMaterialLine,
    SxSubcontractOrder,
    SxTeamDivisionMap,
    SxTeamWorkClose,
    SxTeamHrMap,
    SxWipBalance,
    SxWipHandover,
    SxWipReturn,
    SxWorkAssignment,
    SxWorkCenter,
)

# IE / Master data mã công đoạn sản xuất
from san_xuat.ie_models import (  # noqa: E402,F401
    SxMachine,
    SxOperation,
    SxOperationGroup,
    SxProcessStage,
    SxProductPart,
    SxRouting,
    SxRoutingLine,
    SxSkillLevel,
    SxSmvBasis,
    SxSmvSource,
    SxStitchClass,
    SxTimeStudy,
)
