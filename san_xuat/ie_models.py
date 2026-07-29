"""Master data Mã Công Đoạn Sản Xuất (IE / Industrial Engineering).

Mô hình hoá bộ dữ liệu chuẩn công đoạn của khối sản xuất Just Play:

- Danh mục nền: máy móc, lớp mũi may, bậc kỹ năng, nguồn SMV, khâu sản xuất.
- Thư viện công đoạn chuẩn (OP_CODE + OP_REV) với SMV thư viện.
- Routing theo mã hàng (SMV áp dụng, snapshot revision, chênh lệch).
- Dữ liệu bấm giờ (time study) để hiệu chỉnh SMV.

Quy ước đơn vị:
- SMV lưu theo PHÚT/1 đơn vị cơ sở (khớp từ điển dữ liệu BASE_SMV_MIN).
- Thời gian bấm giờ lưu theo GIÂY.
- Năng suất lý thuyết = 60 / SMV (cái/giờ), ca 10 giờ = 600 / SMV.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


def _q(value: Decimal, places: str = '0.0001') -> Decimal:
    return value.quantize(Decimal(places))


# ---------------------------------------------------------------------------
# Bước 1 — Danh mục nền (reference catalogs)
# ---------------------------------------------------------------------------


class SxRefBase(models.Model):
    """Danh mục tra cứu đơn giản: mã + tên + thứ tự + trạng thái."""

    code = models.CharField(max_length=40, unique=True, db_index=True, verbose_name='Mã')
    name = models.CharField(max_length=150, verbose_name='Tên')
    sort_order = models.PositiveSmallIntegerField(default=100, db_index=True, verbose_name='Thứ tự')
    is_active = models.BooleanField(default=True, db_index=True, verbose_name='Đang dùng')
    notes = models.CharField(max_length=255, blank=True, default='', verbose_name='Ghi chú')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ['sort_order', 'code']

    def __str__(self) -> str:
        return f'{self.code} — {self.name}' if self.name else self.code


class SxMachine(SxRefBase):
    """Danh mục máy móc / thiết bị (MACHINE_CODE)."""

    class Meta(SxRefBase.Meta):
        verbose_name = 'Máy móc SX'
        verbose_name_plural = 'Máy móc SX'


class SxStitchClass(SxRefBase):
    """Lớp mũi may (STITCH_CLASS) — 301, 401, 504…"""

    class Meta(SxRefBase.Meta):
        verbose_name = 'Lớp mũi may'
        verbose_name_plural = 'Lớp mũi may'


class SxSkillLevel(SxRefBase):
    """Bậc kỹ năng (SKILL_LEVEL) — Bậc 1..5."""

    class Meta(SxRefBase.Meta):
        verbose_name = 'Bậc kỹ năng'
        verbose_name_plural = 'Bậc kỹ năng'


class SxSmvSource(SxRefBase):
    """Nguồn hình thành SMV (SMV_SOURCE) — Time study, PMTS/GSD, Ước tính IE…"""

    class Meta(SxRefBase.Meta):
        verbose_name = 'Nguồn SMV'
        verbose_name_plural = 'Nguồn SMV'


class SxProcessStage(SxRefBase):
    """Khâu sản xuất (PROCESS_STAGE) — Cắt, May lắp ráp, Hoàn thiện…"""

    class Meta(SxRefBase.Meta):
        verbose_name = 'Khâu sản xuất'
        verbose_name_plural = 'Khâu sản xuất'


# ---------------------------------------------------------------------------
# Bước 2 — Nhóm công đoạn + Thư viện công đoạn chuẩn
# ---------------------------------------------------------------------------


class SxOperationGroup(models.Model):
    """Nhóm công đoạn (GROUP_CODE) — 01_DM_NHOM_CONG_DOAN."""

    code = models.CharField(max_length=30, unique=True, db_index=True, verbose_name='Mã nhóm')
    name = models.CharField(max_length=150, verbose_name='Tên nhóm')
    process_stage = models.ForeignKey(
        SxProcessStage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='operation_groups',
        verbose_name='Khâu sản xuất',
    )
    process_stage_label = models.CharField(max_length=100, blank=True, default='', verbose_name='Khâu SX (nhãn)')
    product_part = models.CharField(max_length=120, blank=True, default='', verbose_name='Cụm chi tiết')
    description = models.TextField(blank=True, default='', verbose_name='Mô tả')
    default_work_center = models.ForeignKey(
        'san_xuat.SxWorkCenter',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='operation_groups',
        verbose_name='Bộ phận mặc định',
    )
    default_work_center_code = models.CharField(max_length=40, blank=True, default='', verbose_name='Bộ phận mặc định (mã)')
    data_owner = models.CharField(max_length=120, blank=True, default='', verbose_name='Bộ phận quản lý')
    effective_from = models.DateField(null=True, blank=True, verbose_name='Ngày hiệu lực')
    sort_order = models.PositiveSmallIntegerField(default=100, db_index=True, verbose_name='Thứ tự')
    is_active = models.BooleanField(default=True, db_index=True, verbose_name='Đang dùng')
    notes = models.CharField(max_length=255, blank=True, default='', verbose_name='Ghi chú')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'code']
        verbose_name = 'Nhóm công đoạn'
        verbose_name_plural = 'Nhóm công đoạn'

    def __str__(self) -> str:
        return f'{self.code} — {self.name}'


class SxOperation(models.Model):
    """Công đoạn chuẩn (OP_CODE + OP_REV) — 02_THU_VIEN_CONG_DOAN."""

    STATUS_DRAFT = 'draft'
    STATUS_TRIAL = 'trial'
    STATUS_APPROVED = 'approved'
    STATUS_RETIRED = 'retired'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Nháp'),
        (STATUS_TRIAL, 'Thử nghiệm'),
        (STATUS_APPROVED, 'Đã duyệt'),
        (STATUS_RETIRED, 'Ngưng sử dụng'),
    ]

    group = models.ForeignKey(
        SxOperationGroup,
        on_delete=models.PROTECT,
        related_name='operations',
        verbose_name='Nhóm công đoạn',
    )
    op_code = models.CharField(max_length=30, db_index=True, verbose_name='Mã công đoạn')
    op_rev = models.CharField(max_length=10, default='R01', verbose_name='Phiên bản')
    name_vi = models.CharField(max_length=200, verbose_name='Tên công đoạn')
    name_en = models.CharField(max_length=200, blank=True, default='', verbose_name='Tên (EN)')

    process_stage_label = models.CharField(max_length=100, blank=True, default='', verbose_name='Khâu SX')
    product_part = models.CharField(max_length=120, blank=True, default='', verbose_name='Cụm chi tiết')
    method_variant = models.TextField(blank=True, default='', verbose_name='Mô tả phương pháp')
    input_state = models.CharField(max_length=150, blank=True, default='', verbose_name='Trạng thái đầu vào')
    output_state = models.CharField(max_length=150, blank=True, default='', verbose_name='Trạng thái đầu ra')

    machine = models.ForeignKey(
        SxMachine,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='operations',
        verbose_name='Máy móc',
    )
    machine_code = models.CharField(max_length=40, blank=True, default='', verbose_name='Máy (mã)')
    stitch_class = models.ForeignKey(
        SxStitchClass,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='operations',
        verbose_name='Lớp mũi may',
    )
    thread_needle = models.CharField(max_length=120, blank=True, default='', verbose_name='Quy định kim/chỉ')
    attachment_code = models.CharField(max_length=120, blank=True, default='', verbose_name='Mã cữ/gá/chân vịt')

    smv_basis = models.CharField(max_length=60, blank=True, default='', verbose_name='Đơn vị cơ sở SMV')
    skill_level = models.ForeignKey(
        SxSkillLevel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='operations',
        verbose_name='Bậc kỹ năng',
    )
    skill_level_label = models.CharField(max_length=60, blank=True, default='', verbose_name='Bậc (nhãn)')
    qc_criteria = models.TextField(blank=True, default='', verbose_name='Tiêu chí chất lượng')

    base_smv_min = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='SMV thư viện (phút)',
        help_text='SMV chuẩn trên một đơn vị cơ sở, đơn vị phút.',
    )
    smv_source = models.ForeignKey(
        SxSmvSource,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='operations',
        verbose_name='Nguồn SMV',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True, verbose_name='Trạng thái')

    effective_from = models.DateField(null=True, blank=True, verbose_name='Ngày hiệu lực')
    effective_to = models.DateField(null=True, blank=True, verbose_name='Ngày hết hiệu lực')
    ie_owner = models.CharField(max_length=120, blank=True, default='', verbose_name='Người quản lý')
    approved_by = models.CharField(max_length=120, blank=True, default='', verbose_name='Người duyệt')
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name='Ngày duyệt')
    revision_reason = models.CharField(max_length=255, blank=True, default='', verbose_name='Lý do phiên bản')
    work_instruction_url = models.URLField(max_length=500, blank=True, default='', verbose_name='Link hướng dẫn')
    video_url = models.URLField(max_length=500, blank=True, default='', verbose_name='Link video')
    notes = models.CharField(max_length=255, blank=True, default='', verbose_name='Ghi chú')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['op_code', 'op_rev']
        verbose_name = 'Công đoạn chuẩn'
        verbose_name_plural = 'Thư viện công đoạn'
        constraints = [
            models.UniqueConstraint(fields=['op_code', 'op_rev'], name='sx_operation_unique_code_rev'),
        ]

    def __str__(self) -> str:
        return f'{self.op_code}/{self.op_rev} — {self.name_vi}'

    @property
    def std_capacity_pcs_hour(self) -> Decimal:
        if not self.base_smv_min:
            return Decimal('0')
        return _q(Decimal('60') / self.base_smv_min, '0.01')

    @property
    def std_capacity_pcs_10h(self) -> Decimal:
        if not self.base_smv_min:
            return Decimal('0')
        return _q(Decimal('600') / self.base_smv_min, '0.01')


# ---------------------------------------------------------------------------
# Bước 3 — Routing theo mã hàng
# ---------------------------------------------------------------------------


class SxRouting(models.Model):
    """Quy trình mã hàng (ROUTING_ID = STYLE + REV) — 03_ROUTING_MA_HANG (header)."""

    APPROVAL_DRAFT = 'draft'
    APPROVAL_PENDING = 'pending'
    APPROVAL_APPROVED = 'approved'
    APPROVAL_REJECTED = 'rejected'
    APPROVAL_CHOICES = [
        (APPROVAL_DRAFT, 'Nháp'),
        (APPROVAL_PENDING, 'Chờ duyệt'),
        (APPROVAL_APPROVED, 'Đã duyệt'),
        (APPROVAL_REJECTED, 'Từ chối'),
    ]

    routing_id = models.CharField(max_length=80, unique=True, db_index=True, verbose_name='Mã routing')
    style_code = models.CharField(max_length=60, db_index=True, verbose_name='Mã hàng')
    style_name = models.CharField(max_length=255, blank=True, default='', verbose_name='Tên mã hàng')
    product_family = models.CharField(max_length=150, blank=True, default='', verbose_name='Nhóm sản phẩm')
    routing_rev = models.CharField(max_length=10, default='R01', verbose_name='Phiên bản quy trình')
    tech_doc = models.ForeignKey(
        'san_xuat.ProductTechDoc',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='routings',
        verbose_name='Hồ sơ SX',
    )
    effective_from = models.DateField(null=True, blank=True, verbose_name='Ngày hiệu lực')
    is_active = models.BooleanField(default=True, db_index=True, verbose_name='Đang áp dụng')
    approval_status = models.CharField(
        max_length=20,
        choices=APPROVAL_CHOICES,
        default=APPROVAL_DRAFT,
        db_index=True,
        verbose_name='Trạng thái duyệt',
    )
    ie_owner = models.CharField(max_length=120, blank=True, default='', verbose_name='Người lập')
    approved_by = models.CharField(max_length=120, blank=True, default='', verbose_name='Người duyệt')
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name='Ngày duyệt')
    notes = models.CharField(max_length=255, blank=True, default='', verbose_name='Ghi chú')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sx_routings_created',
        verbose_name='Người tạo',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['style_code', 'routing_rev']
        verbose_name = 'Routing mã hàng'
        verbose_name_plural = 'Routing mã hàng'

    def __str__(self) -> str:
        return self.routing_id

    @property
    def total_smv(self) -> Decimal:
        total = self.lines.aggregate(s=models.Sum('total_operation_smv'))['s'] or Decimal('0')
        return _q(total, '0.0001')

    @property
    def operation_count(self) -> int:
        return self.lines.count()

    @property
    def is_approved(self) -> bool:
        return self.approval_status == self.APPROVAL_APPROVED


class SxRoutingLine(models.Model):
    """Dòng routing (công đoạn theo thứ tự) — 03_ROUTING_MA_HANG (line)."""

    routing = models.ForeignKey(
        SxRouting,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name='Routing',
    )
    seq_no = models.PositiveIntegerField(default=10, verbose_name='Thứ tự')
    operation = models.ForeignKey(
        SxOperation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='routing_lines',
        verbose_name='Công đoạn (thư viện)',
    )
    op_code = models.CharField(max_length=30, db_index=True, verbose_name='Mã công đoạn')
    op_rev = models.CharField(max_length=10, default='R01', verbose_name='Phiên bản CĐ (snapshot)')
    op_name_vi = models.CharField(max_length=200, blank=True, default='', verbose_name='Tên công đoạn')
    group_code = models.CharField(max_length=30, blank=True, default='', verbose_name='Mã nhóm')

    qty_per_garment = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=Decimal('1'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='SL/sản phẩm',
    )
    library_unit_smv = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal('0'),
        verbose_name='SMV thư viện (phút)',
    )
    applied_unit_smv = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='SMV áp dụng (phút)',
    )
    total_operation_smv = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=Decimal('0'),
        verbose_name='Tổng SMV',
        help_text='SL/SP × SMV áp dụng.',
    )
    smv_variance_pct = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name='Chênh lệch SMV (%)',
    )

    machine = models.ForeignKey(
        SxMachine,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='routing_lines',
        verbose_name='Máy móc',
    )
    machine_code = models.CharField(max_length=40, blank=True, default='', verbose_name='Máy (mã)')
    work_center = models.ForeignKey(
        'san_xuat.SxWorkCenter',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='routing_lines',
        verbose_name='Bộ phận chịu trách nhiệm',
    )
    work_center_code = models.CharField(max_length=40, blank=True, default='', verbose_name='Bộ phận (mã)')
    predecessor_seq = models.PositiveIntegerField(null=True, blank=True, verbose_name='Công đoạn trước')
    parallel_group = models.CharField(max_length=40, blank=True, default='', verbose_name='Nhóm song song')
    bundle_size = models.PositiveIntegerField(null=True, blank=True, verbose_name='Cỡ bó')
    skill_level_label = models.CharField(max_length=60, blank=True, default='', verbose_name='Bậc kỹ năng')
    critical_qc = models.BooleanField(default=False, verbose_name='QC trọng yếu')
    target_efficiency = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name='Hiệu suất mục tiêu (%)',
    )
    notes = models.CharField(max_length=255, blank=True, default='', verbose_name='Ghi chú')
    variance_explanation = models.CharField(
        max_length=500,
        blank=True,
        default='',
        verbose_name='Giải trình lệch SMV',
        help_text='Bắt buộc khi |chênh lệch| > 15% trước khi duyệt phát hành.',
    )

    class Meta:
        ordering = ['routing', 'seq_no']
        verbose_name = 'Dòng routing'
        verbose_name_plural = 'Dòng routing'
        constraints = [
            models.UniqueConstraint(fields=['routing', 'seq_no'], name='sx_routing_unique_seq'),
        ]

    def __str__(self) -> str:
        return f'{self.routing_id}#{self.seq_no} {self.op_code}'

    def recompute(self) -> None:
        """Tính tổng SMV và chênh lệch so với thư viện."""
        self.total_operation_smv = _q((self.qty_per_garment or Decimal('0')) * (self.applied_unit_smv or Decimal('0')))
        if self.library_unit_smv:
            diff = (self.applied_unit_smv - self.library_unit_smv) / self.library_unit_smv * Decimal('100')
            self.smv_variance_pct = _q(diff, '0.01')
        else:
            self.smv_variance_pct = Decimal('0')

    def save(self, *args, **kwargs):
        self.recompute()
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Bước 4 — Dữ liệu bấm giờ (time study)
# ---------------------------------------------------------------------------


class SxTimeStudy(models.Model):
    """Quan sát bấm giờ (STUDY_ID) — 04_DU_LIEU_TIME_STUDY."""

    APPROVAL_PENDING = 'pending'
    APPROVAL_APPROVED = 'approved'
    APPROVAL_REJECTED = 'rejected'
    APPROVAL_REMEASURE = 'remeasure'
    APPROVAL_CHOICES = [
        (APPROVAL_PENDING, 'Chờ duyệt'),
        (APPROVAL_APPROVED, 'Đã duyệt'),
        (APPROVAL_REJECTED, 'Từ chối'),
        (APPROVAL_REMEASURE, 'Cần đo lại'),
    ]

    study_id = models.CharField(max_length=40, unique=True, db_index=True, verbose_name='Mã quan sát')
    study_date = models.DateField(null=True, blank=True, verbose_name='Ngày đo')
    factory_code = models.CharField(max_length=40, blank=True, default='', verbose_name='Nhà máy')
    line_code = models.CharField(max_length=40, blank=True, default='', verbose_name='Chuyền')
    shift = models.CharField(max_length=40, blank=True, default='', verbose_name='Ca')
    style_code = models.CharField(max_length=60, blank=True, default='', db_index=True, verbose_name='Mã hàng')
    routing_rev = models.CharField(max_length=10, blank=True, default='', verbose_name='Routing rev')

    operation = models.ForeignKey(
        SxOperation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='time_studies',
        verbose_name='Công đoạn (thư viện)',
    )
    op_code = models.CharField(max_length=30, db_index=True, verbose_name='Mã công đoạn')
    op_rev = models.CharField(max_length=10, default='R01', verbose_name='Phiên bản CĐ')
    op_name_vi = models.CharField(max_length=200, blank=True, default='', verbose_name='Tên công đoạn')

    operator_id = models.CharField(max_length=40, blank=True, default='', verbose_name='Mã công nhân')
    skill_level_label = models.CharField(max_length=60, blank=True, default='', verbose_name='Bậc kỹ năng')
    machine = models.ForeignKey(
        SxMachine,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='time_studies',
        verbose_name='Máy móc',
    )
    machine_code = models.CharField(max_length=40, blank=True, default='', verbose_name='Máy (mã)')
    method_rev = models.CharField(max_length=10, blank=True, default='', verbose_name='Phiên bản thao tác')
    obs_no = models.PositiveIntegerField(default=1, verbose_name='Số quan sát')

    observed_cycle_sec = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Chu kỳ quan sát (giây)',
    )
    abnormal_sec = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Thời gian bất thường (giây)',
    )
    performance_rating = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        default=Decimal('1'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Hệ số tốc độ',
        help_text='Ví dụ 1.00 = 100%.',
    )
    allowance_pct = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Phụ cấp (%)',
    )
    current_routing_smv = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal('0'),
        verbose_name='SMV routing hiện tại (phút)',
    )

    # Giá trị tính toán (lưu để lọc/báo cáo, cập nhật trong save()).
    net_observed_sec = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'), verbose_name='Net (giây)')
    normal_time_sec = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'), verbose_name='Normal (giây)')
    standard_time_sec = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'), verbose_name='Standard (giây)')
    calculated_smv = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal('0'), verbose_name='SMV tính toán (phút)')
    variance_pct = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0'), verbose_name='Chênh lệch (%)')

    ie_observer = models.CharField(max_length=60, blank=True, default='', verbose_name='IE đo')
    conditions = models.CharField(max_length=255, blank=True, default='', verbose_name='Điều kiện đo')
    approval_status = models.CharField(
        max_length=20,
        choices=APPROVAL_CHOICES,
        default=APPROVAL_PENDING,
        db_index=True,
        verbose_name='Trạng thái duyệt',
    )
    variance_explanation = models.CharField(
        max_length=500,
        blank=True,
        default='',
        verbose_name='Giải trình lệch SMV',
        help_text='Bắt buộc khi |chênh lệch| > 15% lúc duyệt cập nhật routing.',
    )
    notes = models.CharField(max_length=255, blank=True, default='', verbose_name='Ghi chú')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['op_code', 'obs_no', 'study_id']
        verbose_name = 'Bấm giờ (time study)'
        verbose_name_plural = 'Bấm giờ (time study)'

    def __str__(self) -> str:
        return f'{self.study_id} — {self.op_code}'

    def recompute(self) -> None:
        observed = self.observed_cycle_sec or Decimal('0')
        abnormal = self.abnormal_sec or Decimal('0')
        rating = self.performance_rating or Decimal('0')
        if rating <= 0:
            # Mẫu import thường để trống/0 → mặc định 100%.
            rating = Decimal('1')
        allowance = self.allowance_pct or Decimal('0')

        net = observed - abnormal
        if net < 0:
            net = Decimal('0')
        normal = net * rating
        standard = normal * (Decimal('1') + allowance / Decimal('100'))
        smv = standard / Decimal('60')

        self.net_observed_sec = _q(net, '0.01')
        self.normal_time_sec = _q(normal, '0.01')
        self.standard_time_sec = _q(standard, '0.01')
        self.calculated_smv = _q(smv, '0.0001')
        if self.current_routing_smv:
            diff = (smv - self.current_routing_smv) / self.current_routing_smv * Decimal('100')
            self.variance_pct = _q(diff, '0.01')
        else:
            self.variance_pct = Decimal('0')

    def save(self, *args, **kwargs):
        self.recompute()
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Nhật ký IE (import / duyệt / đổi SMV)
# ---------------------------------------------------------------------------


class SxIeAuditLog(models.Model):
    """Nhật ký thao tác master data công đoạn (IE)."""

    ACTION_IMPORT = 'import'
    ACTION_EXPORT = 'export'
    ACTION_APPROVE = 'approve'
    ACTION_REJECT = 'reject'
    ACTION_SMV_CHANGE = 'smv_change'
    ACTION_UPDATE = 'update'
    ACTION_CREATE = 'create'
    ACTION_LINK = 'link'
    ACTION_CHOICES = [
        (ACTION_IMPORT, 'Import'),
        (ACTION_EXPORT, 'Xuất Excel'),
        (ACTION_APPROVE, 'Duyệt'),
        (ACTION_REJECT, 'Từ chối'),
        (ACTION_SMV_CHANGE, 'Đổi SMV'),
        (ACTION_UPDATE, 'Cập nhật'),
        (ACTION_CREATE, 'Tạo mới'),
        (ACTION_LINK, 'Gắn liên kết'),
    ]

    action = models.CharField(max_length=20, choices=ACTION_CHOICES, db_index=True)
    object_type = models.CharField(max_length=40, blank=True, default='', db_index=True)
    object_id = models.CharField(max_length=80, blank=True, default='', db_index=True)
    object_repr = models.CharField(max_length=255, blank=True, default='')
    summary = models.CharField(max_length=500, blank=True, default='')
    changes = models.JSONField(default=dict, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sx_ie_audit_logs',
    )
    username = models.CharField(max_length=150, blank=True, default='', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Nhật ký IE'
        verbose_name_plural = 'Nhật ký IE'

    def __str__(self) -> str:
        return f'{self.action} {self.object_repr or self.object_id}'
