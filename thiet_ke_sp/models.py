"""Hồ sơ thiết kế sản phẩm: từ đề xuất ý tưởng đến bàn giao mẫu chuẩn cho sản xuất."""

from __future__ import annotations

import os
import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import get_valid_filename
from django_cleanup import cleanup

from san_xuat.design_nas_storage import DesignDocNasStorage

USER = settings.AUTH_USER_MODEL


class Status(models.TextChoices):
    DRAFT = 'draft', 'Nháp'
    BRIEF_PENDING = 'brief_pending', 'Chờ duyệt đề bài'
    BRIEF_NEEDS_INFO = 'brief_needs_info', 'Cần bổ sung đề bài'
    DESIGNING = 'designing', 'Đang thiết kế'
    DESIGN_PENDING = 'design_pending', 'Chờ duyệt thiết kế'
    DESIGN_REVISE = 'design_revise', 'Cần chỉnh thiết kế'
    SAMPLING = 'sampling', 'Đang làm mẫu'
    SAMPLE_EVAL_PENDING = 'sample_eval_pending', 'Chờ đánh giá mẫu'
    SAMPLE_REVISE = 'sample_revise', 'Cần sửa mẫu'
    MASTER_PENDING = 'master_pending', 'Chờ duyệt mẫu chuẩn'
    APPROVED = 'approved', 'Đã duyệt sản xuất'
    HANDED_OVER = 'handed_over', 'Đã bàn giao'
    PAUSED = 'paused', 'Tạm dừng'
    CANCELLED = 'cancelled', 'Đã hủy'
    CLOSED = 'closed', 'Đã đóng hồ sơ'


IN_PROGRESS_STATUSES = (
    Status.DESIGNING,
    Status.DESIGN_PENDING,
    Status.DESIGN_REVISE,
    Status.SAMPLING,
    Status.SAMPLE_EVAL_PENDING,
    Status.SAMPLE_REVISE,
    Status.MASTER_PENDING,
)
DONE_STATUSES = (Status.HANDED_OVER, Status.CLOSED)
STOPPED_STATUSES = (Status.PAUSED, Status.CANCELLED)
FINAL_STATUSES = (Status.CANCELLED, Status.CLOSED)

STATUS_BADGES = {
    Status.DRAFT: 'secondary',
    Status.BRIEF_PENDING: 'warning',
    Status.BRIEF_NEEDS_INFO: 'danger',
    Status.DESIGNING: 'primary',
    Status.DESIGN_PENDING: 'warning',
    Status.DESIGN_REVISE: 'danger',
    Status.SAMPLING: 'primary',
    Status.SAMPLE_EVAL_PENDING: 'warning',
    Status.SAMPLE_REVISE: 'danger',
    Status.MASTER_PENDING: 'warning',
    Status.APPROVED: 'success',
    Status.HANDED_OVER: 'success',
    Status.PAUSED: 'secondary',
    Status.CANCELLED: 'dark',
    Status.CLOSED: 'dark',
}

STATUS_TONES = {
    Status.DRAFT: 'gray',
    Status.BRIEF_PENDING: 'amber',
    Status.BRIEF_NEEDS_INFO: 'red',
    Status.DESIGNING: 'blue',
    Status.DESIGN_PENDING: 'amber',
    Status.DESIGN_REVISE: 'red',
    Status.SAMPLING: 'blue',
    Status.SAMPLE_EVAL_PENDING: 'amber',
    Status.SAMPLE_REVISE: 'red',
    Status.MASTER_PENDING: 'purple',
    Status.APPROVED: 'green',
    Status.HANDED_OVER: 'green',
    Status.PAUSED: 'gray',
    Status.CANCELLED: 'gray',
    Status.CLOSED: 'dark',
}

# Thứ tự 8 bước trên thanh tiến trình (mục 3 tài liệu nghiệp vụ).
STEPS = (
    ('proposal', 'Đề xuất', (Status.DRAFT, Status.BRIEF_NEEDS_INFO)),
    ('brief', 'Duyệt đề bài', (Status.BRIEF_PENDING,)),
    ('design', 'Thiết kế', (Status.DESIGNING, Status.DESIGN_REVISE)),
    ('design_approval', 'Duyệt thiết kế', (Status.DESIGN_PENDING,)),
    ('sample', 'Làm mẫu', (Status.SAMPLING, Status.SAMPLE_REVISE)),
    ('evaluation', 'Đánh giá mẫu', (Status.SAMPLE_EVAL_PENDING,)),
    ('master', 'Duyệt mẫu chuẩn', (Status.MASTER_PENDING,)),
    ('handover', 'Bàn giao SX', (Status.APPROVED, Status.HANDED_OVER, Status.CLOSED)),
)


class ProductGroup(models.TextChoices):
    FOOTBALL = 'bong_da', 'Bóng đá'
    VOLLEYBALL = 'bong_chuyen', 'Bóng chuyền'
    RACKET = 'cau_long_pickleball', 'Cầu lông / Pickleball'
    BASKETBALL = 'bong_ro', 'Bóng rổ'
    RUNNING = 'chay_bo', 'Chạy bộ'
    TEAMWEAR = 'polo_teamwear', 'Polo / Teamwear'
    BASIC = 'basic', 'Basic'
    OTHER = 'khac', 'Nhóm khác'


class ProductType(models.TextChoices):
    SHIRT = 'ao', 'Áo'
    PANTS = 'quan', 'Quần'
    SET = 'bo', 'Bộ'
    JACKET = 'ao_khoac', 'Áo khoác'
    POLO = 'polo', 'Polo'
    ACCESSORY = 'phu_kien', 'Phụ kiện'
    OTHER = 'khac', 'Khác'


class Priority(models.TextChoices):
    URGENT = 'urgent', 'Khẩn'
    HIGH = 'high', 'Cao'
    NORMAL = 'normal', 'Bình thường'
    LOW = 'low', 'Thấp'


PRIORITY_BADGES = {
    Priority.URGENT: 'danger',
    Priority.HIGH: 'warning',
    Priority.NORMAL: 'info',
    Priority.LOW: 'secondary',
}


class Role(models.TextChoices):
    PROPOSER = 'proposer', 'Người đề xuất'
    OWNER = 'owner', 'Người phụ trách chính'
    APPROVER = 'approver', 'Người duyệt'
    DESIGNER = 'designer', 'Thiết kế / R&D'
    TECHNICIAN = 'technician', 'Kỹ thuật / Tài liệu kỹ thuật'
    SAMPLE_MAKER = 'sample_maker', 'May mẫu'
    QA = 'qa_user', 'QA/QC'
    COSTING = 'costing_user', 'Kế hoạch / Giá thành'
    RECEIVER = 'receiver', 'Bộ phận nhận bàn giao'
    CONDITION = 'condition', 'Xử lý điều kiện duyệt'


# Vai trò gán sẵn trên hồ sơ — tên field trùng value của Role.
DOSSIER_ROLE_FIELDS = (
    Role.OWNER,
    Role.APPROVER,
    Role.DESIGNER,
    Role.TECHNICIAN,
    Role.SAMPLE_MAKER,
    Role.QA,
    Role.COSTING,
)


class DossierSequence(models.Model):
    """Bộ đếm mã PTSP-YYYY-NNNN theo năm (khoá dòng khi cấp mã)."""

    year = models.PositiveIntegerField(primary_key=True)
    last_no = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Bộ đếm mã hồ sơ'
        verbose_name_plural = 'Bộ đếm mã hồ sơ'


class ProductDevelopment(models.Model):
    code = models.CharField(max_length=20, unique=True, verbose_name='Mã hồ sơ')
    name = models.CharField(max_length=255, verbose_name='Tên sản phẩm tạm thời')
    product_group = models.CharField(
        max_length=30, choices=ProductGroup.choices, default=ProductGroup.OTHER, verbose_name='Nhóm sản phẩm',
    )
    product_type = models.CharField(
        max_length=20, choices=ProductType.choices, default=ProductType.SHIRT, verbose_name='Loại sản phẩm',
    )
    collection = models.CharField(max_length=120, blank=True, default='', verbose_name='Bộ sưu tập / mùa bán hàng')
    target_customer = models.CharField(max_length=255, blank=True, default='', verbose_name='Khách hàng mục tiêu')
    usage_need = models.TextField(blank=True, default='', verbose_name='Nhu cầu sử dụng')
    market_need = models.TextField(blank=True, default='', verbose_name='Nhu cầu thị trường / phân khúc')
    priority = models.CharField(
        max_length=10, choices=Priority.choices, default=Priority.NORMAL, verbose_name='Mức độ ưu tiên',
    )
    proposer = models.ForeignKey(
        USER, on_delete=models.PROTECT, related_name='tksp_proposed', verbose_name='Người đề xuất',
    )
    owner = models.ForeignKey(
        USER, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tksp_owned', verbose_name='Người phụ trách chính',
    )
    approver = models.ForeignKey(
        USER, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tksp_approving', verbose_name='Người duyệt',
    )
    designer = models.ForeignKey(
        USER, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tksp_designing', verbose_name='Thiết kế / R&D',
    )
    technician = models.ForeignKey(
        USER, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tksp_technical', verbose_name='Kỹ thuật / Tài liệu kỹ thuật',
    )
    sample_maker = models.ForeignKey(
        USER, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tksp_sampling', verbose_name='May mẫu',
    )
    qa_user = models.ForeignKey(
        USER, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tksp_qa', verbose_name='QA/QC',
    )
    costing_user = models.ForeignKey(
        USER, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tksp_costing', verbose_name='Kế hoạch / Giá thành',
    )
    proposed_date = models.DateField(default=timezone.localdate, verbose_name='Ngày đề xuất')
    launch_date = models.DateField(null=True, blank=True, verbose_name='Ngày dự kiến ra mắt')
    expected_qty = models.PositiveIntegerField(null=True, blank=True, verbose_name='Sản lượng dự kiến')
    target_wholesale_price = models.DecimalField(
        max_digits=14, decimal_places=0, null=True, blank=True, verbose_name='Giá bán sỉ mục tiêu',
    )
    target_retail_price = models.DecimalField(
        max_digits=14, decimal_places=0, null=True, blank=True, verbose_name='Giá bán lẻ mục tiêu',
    )
    target_cost = models.DecimalField(
        max_digits=14, decimal_places=0, null=True, blank=True, verbose_name='Giá thành mục tiêu',
    )
    reference_links = models.TextField(blank=True, default='', verbose_name='Sản phẩm / đường dẫn tham khảo')
    description = models.TextField(blank=True, default='', verbose_name='Mô tả ý tưởng')

    estimated_cost = models.DecimalField(
        max_digits=14, decimal_places=0, null=True, blank=True, verbose_name='Giá thành dự kiến',
    )
    post_sample_cost = models.DecimalField(
        max_digits=14, decimal_places=0, null=True, blank=True, verbose_name='Giá thành sau mẫu',
    )
    proposed_wholesale_price = models.DecimalField(
        max_digits=14, decimal_places=0, null=True, blank=True, verbose_name='Giá bán sỉ đề xuất',
    )
    proposed_retail_price = models.DecimalField(
        max_digits=14, decimal_places=0, null=True, blank=True, verbose_name='Giá bán lẻ đề xuất',
    )
    cost_note = models.TextField(blank=True, default='', verbose_name='Ghi chú giá thành')

    status = models.CharField(
        max_length=30, choices=Status.choices, default=Status.DRAFT, db_index=True, verbose_name='Trạng thái',
    )
    status_changed_at = models.DateTimeField(default=timezone.now, verbose_name='Đổi trạng thái lúc')
    submitted_at = models.DateTimeField(null=True, blank=True, verbose_name='Gửi duyệt đề bài lúc')
    paused_from_status = models.CharField(max_length=30, blank=True, default='', choices=Status.choices)
    stop_reason = models.TextField(blank=True, default='', verbose_name='Lý do tạm dừng / hủy')
    is_locked = models.BooleanField(default=False, verbose_name='Khóa dữ liệu chính')
    official_product_code = models.CharField(
        max_length=60, blank=True, default='', db_index=True, verbose_name='Mã sản phẩm chính thức',
    )
    approved_design_version = models.ForeignKey(
        'DesignVersion', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name='Phiên bản thiết kế được duyệt',
    )
    final_sample_version = models.ForeignKey(
        'SampleVersion', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name='Mẫu chuẩn',
    )
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name='Duyệt sản xuất lúc')
    closed_at = models.DateTimeField(null=True, blank=True, verbose_name='Đóng hồ sơ lúc')
    is_demo = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        verbose_name = 'Hồ sơ thiết kế sản phẩm'
        verbose_name_plural = 'Hồ sơ thiết kế sản phẩm'

    def __str__(self):
        return f'{self.code} — {self.name}'

    def get_absolute_url(self):
        return reverse('thiet_ke_sp:detail', args=[self.pk])

    @property
    def status_badge(self) -> str:
        return STATUS_BADGES.get(self.status, 'secondary')

    @property
    def priority_badge(self) -> str:
        return PRIORITY_BADGES.get(self.priority, 'secondary')

    @property
    def status_tone(self) -> str:
        return STATUS_TONES.get(self.status, 'gray')

    @property
    def step_no(self) -> int:
        status = self.paused_from_status if self.status == Status.PAUSED and self.paused_from_status else self.status
        for index, (_key, _label, statuses) in enumerate(STEPS, start=1):
            if status in statuses:
                return index
        return 1

    @property
    def step_total(self) -> int:
        return len(STEPS)

    @property
    def step_pct(self) -> int:
        if self.status in DONE_STATUSES:
            return 100
        return round((self.step_no - 1) * 100 / len(STEPS))

    @property
    def cost_for_variance(self) -> Decimal | None:
        return self.post_sample_cost if self.post_sample_cost is not None else self.estimated_cost

    @property
    def cost_variance(self) -> Decimal | None:
        cost = self.cost_for_variance
        if cost is None or self.target_cost is None:
            return None
        return cost - self.target_cost

    @property
    def cost_variance_pct(self) -> Decimal | None:
        variance = self.cost_variance
        if variance is None or not self.target_cost:
            return None
        return (variance * 100 / self.target_cost).quantize(Decimal('0.1'))

    def current_design_version(self):
        return self.design_versions.filter(is_current=True).first()

    def current_sample_version(self):
        return self.sample_versions.filter(is_current=True).first()

    def role_user(self, role: str):
        return getattr(self, role, None) if role in DOSSIER_ROLE_FIELDS else None


class DesignVersion(models.Model):
    STATE_DRAFT = 'draft'
    STATE_SUBMITTED = 'submitted'
    STATE_APPROVED = 'approved'
    STATE_REJECTED = 'rejected'
    STATE_CHOICES = [
        (STATE_DRAFT, 'Đang soạn'),
        (STATE_SUBMITTED, 'Đã gửi duyệt'),
        (STATE_APPROVED, 'Đã duyệt'),
        (STATE_REJECTED, 'Yêu cầu chỉnh'),
    ]

    dossier = models.ForeignKey(ProductDevelopment, on_delete=models.CASCADE, related_name='design_versions')
    version_no = models.PositiveIntegerField(verbose_name='Phiên bản')
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default=STATE_DRAFT)
    is_current = models.BooleanField(default=True, verbose_name='Phiên bản hiện hành')
    style_description = models.TextField(blank=True, default='', verbose_name='Kiểu dáng')
    pattern_description = models.TextField(blank=True, default='', verbose_name='Màu sắc / họa tiết')
    logo_placement = models.TextField(blank=True, default='', verbose_name='Vị trí, kích thước logo / họa tiết')
    materials = models.TextField(blank=True, default='', verbose_name='Chất liệu, nguyên phụ liệu dự kiến')
    highlights = models.TextField(blank=True, default='', verbose_name='Điểm nổi bật')
    change_note = models.TextField(blank=True, default='', verbose_name='Nội dung thay đổi so với bản trước')
    created_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-version_no']
        unique_together = [('dossier', 'version_no')]
        verbose_name = 'Phiên bản thiết kế'
        verbose_name_plural = 'Phiên bản thiết kế'

    def __str__(self):
        return f'{self.dossier.code} {self.label}'

    @property
    def label(self) -> str:
        return f'V{self.version_no}'

    @property
    def is_editable(self) -> bool:
        return self.state == self.STATE_DRAFT and self.is_current


class Colorway(models.Model):
    design_version = models.ForeignKey(DesignVersion, on_delete=models.CASCADE, related_name='colorways')
    name = models.CharField(max_length=120, verbose_name='Tên phối màu')
    color_codes = models.CharField(max_length=255, verbose_name='Mã màu')
    note = models.CharField(max_length=255, blank=True, default='', verbose_name='Ghi chú')
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'pk']
        verbose_name = 'Colorway'
        verbose_name_plural = 'Colorway'

    def __str__(self):
        return self.name


class SampleVersion(models.Model):
    STATE_IN_PROGRESS = 'in_progress'
    STATE_SUBMITTED = 'submitted'
    STATE_PASSED = 'passed'
    STATE_FAILED = 'failed'
    STATE_CHOICES = [
        (STATE_IN_PROGRESS, 'Đang làm'),
        (STATE_SUBMITTED, 'Chờ đánh giá'),
        (STATE_PASSED, 'Đạt'),
        (STATE_FAILED, 'Cần sửa'),
    ]

    dossier = models.ForeignKey(ProductDevelopment, on_delete=models.CASCADE, related_name='sample_versions')
    version_no = models.PositiveIntegerField(verbose_name='Lần làm mẫu')
    design_version = models.ForeignKey(
        DesignVersion, on_delete=models.CASCADE, related_name='samples', verbose_name='Theo thiết kế',
    )
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default=STATE_IN_PROGRESS)
    is_current = models.BooleanField(default=True, verbose_name='Phiên bản hiện hành')
    maker = models.ForeignKey(
        USER, on_delete=models.SET_NULL, null=True, blank=True, related_name='+', verbose_name='Người làm mẫu',
    )
    assigned_date = models.DateField(null=True, blank=True, verbose_name='Ngày giao mẫu')
    completed_date = models.DateField(null=True, blank=True, verbose_name='Ngày hoàn thành')
    progress_note = models.TextField(blank=True, default='', verbose_name='Tiến độ / ghi chú')
    change_note = models.TextField(blank=True, default='', verbose_name='Nội dung sửa so với lần trước')
    created_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-version_no']
        unique_together = [('dossier', 'version_no')]
        verbose_name = 'Phiên bản mẫu'
        verbose_name_plural = 'Phiên bản mẫu'

    def __str__(self):
        return f'{self.dossier.code} {self.label}'

    @property
    def label(self) -> str:
        return f'M{self.version_no}'

    @property
    def is_editable(self) -> bool:
        return self.state == self.STATE_IN_PROGRESS and self.is_current


class TechnicalPack(models.Model):
    sample_version = models.OneToOneField(SampleVersion, on_delete=models.CASCADE, related_name='tech_pack')
    size_spec = models.TextField(blank=True, default='', verbose_name='Bảng thông số kích thước')
    cutting_req = models.TextField(blank=True, default='', verbose_name='Yêu cầu cắt')
    sewing_req = models.TextField(blank=True, default='', verbose_name='Yêu cầu may')
    decoration_req = models.TextField(blank=True, default='', verbose_name='Yêu cầu in / ép / thêu')
    finishing_req = models.TextField(blank=True, default='', verbose_name='Yêu cầu hoàn thiện')
    packing_req = models.TextField(blank=True, default='', verbose_name='Yêu cầu đóng gói')
    updated_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Hồ sơ kỹ thuật'
        verbose_name_plural = 'Hồ sơ kỹ thuật'

    @property
    def material_cost_total(self) -> Decimal:
        total = Decimal('0')
        for line in self.material_lines.all():
            total += line.line_cost or Decimal('0')
        return total


class MaterialLine(models.Model):
    tech_pack = models.ForeignKey(TechnicalPack, on_delete=models.CASCADE, related_name='material_lines')
    material_name = models.CharField(max_length=200, verbose_name='Nguyên phụ liệu')
    is_main = models.BooleanField(default=True, verbose_name='NPL chính')
    spec = models.CharField(max_length=255, blank=True, default='', verbose_name='Quy cách / màu')
    consumption = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True, verbose_name='Định mức',
    )
    unit = models.CharField(max_length=30, blank=True, default='', verbose_name='ĐVT')
    unit_price = models.DecimalField(
        max_digits=14, decimal_places=0, null=True, blank=True, verbose_name='Đơn giá',
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'pk']
        verbose_name = 'Dòng nguyên phụ liệu'
        verbose_name_plural = 'Dòng nguyên phụ liệu'

    @property
    def line_cost(self) -> Decimal | None:
        if self.consumption is None or self.unit_price is None:
            return None
        return (self.consumption * self.unit_price).quantize(Decimal('1'))


class EvaluatorRole(models.TextChoices):
    RND = 'rnd', 'R&D'
    TECHNICAL = 'technical', 'Kỹ thuật'
    QA = 'qa', 'QA/QC'
    COSTING = 'costing', 'Kế hoạch / Giá thành'
    OTHER = 'other', 'Bên liên quan khác'


class Criterion(models.TextChoices):
    APPEARANCE = 'appearance', 'Ngoại quan'
    FORM = 'form', 'Form dáng'
    FIT = 'fit', 'Độ vừa vặn'
    QUALITY = 'quality', 'Chất lượng'
    MANUFACTURABILITY = 'manufacturability', 'Khả năng sản xuất'
    MATERIALS = 'materials', 'Nguyên phụ liệu'
    COST = 'cost', 'Giá thành'


class SampleEvaluation(models.Model):
    RESULT_PASS = 'pass'
    RESULT_FAIL = 'fail'
    RESULT_CHOICES = [(RESULT_PASS, 'Đạt'), (RESULT_FAIL, 'Không đạt')]

    sample_version = models.ForeignKey(SampleVersion, on_delete=models.CASCADE, related_name='evaluations')
    role = models.CharField(max_length=20, choices=EvaluatorRole.choices, verbose_name='Vai trò đánh giá')
    evaluator = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, related_name='+')
    result = models.CharField(max_length=10, choices=RESULT_CHOICES, verbose_name='Kết luận')
    conclusion = models.TextField(blank=True, default='', verbose_name='Nhận xét chung')
    defects = models.TextField(blank=True, default='', verbose_name='Lỗi / nội dung phải chỉnh')
    fix_owner = models.ForeignKey(
        USER, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
        verbose_name='Người chịu trách nhiệm sửa',
    )
    fix_due = models.DateField(null=True, blank=True, verbose_name='Hạn sửa')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Đánh giá mẫu'
        verbose_name_plural = 'Đánh giá mẫu'


class EvaluationItem(models.Model):
    RESULT_PASS = 'pass'
    RESULT_FAIL = 'fail'
    RESULT_NA = 'na'
    RESULT_CHOICES = [(RESULT_PASS, 'Đạt'), (RESULT_FAIL, 'Không đạt'), (RESULT_NA, 'Không đánh giá')]

    evaluation = models.ForeignKey(SampleEvaluation, on_delete=models.CASCADE, related_name='items')
    criterion = models.CharField(max_length=30, choices=Criterion.choices)
    result = models.CharField(max_length=10, choices=RESULT_CHOICES, default=RESULT_NA)
    note = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        ordering = ['pk']


class ApprovalStage(models.TextChoices):
    BRIEF = 'brief', 'Duyệt đề bài'
    DESIGN = 'design', 'Duyệt thiết kế'
    MASTER = 'master', 'Duyệt mẫu chuẩn'
    STOP = 'stop', 'Tạm dừng / Hủy / Tiếp tục'
    CHANGE = 'change', 'Yêu cầu thay đổi sau duyệt'


class ApprovalDecision(models.TextChoices):
    APPROVED = 'approved', 'Duyệt'
    APPROVED_CONDITIONAL = 'approved_conditional', 'Duyệt có điều kiện'
    REQUEST_CHANGE = 'request_change', 'Yêu cầu bổ sung / chỉnh sửa'
    PAUSED = 'paused', 'Tạm dừng'
    RESUMED = 'resumed', 'Tiếp tục'
    CANCELLED = 'cancelled', 'Hủy'


class Approval(models.Model):
    dossier = models.ForeignKey(ProductDevelopment, on_delete=models.CASCADE, related_name='approvals')
    stage = models.CharField(max_length=20, choices=ApprovalStage.choices)
    decision = models.CharField(max_length=30, choices=ApprovalDecision.choices)
    comment = models.TextField(blank=True, default='', verbose_name='Ý kiến')
    design_version = models.ForeignKey(DesignVersion, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    sample_version = models.ForeignKey(SampleVersion, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    decided_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, related_name='+')
    decided_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-decided_at', '-pk']
        verbose_name = 'Phê duyệt'
        verbose_name_plural = 'Phê duyệt'


class ApprovalCondition(models.Model):
    """Điều kiện kèm theo khi duyệt mẫu chuẩn — phải xong hết mới được bàn giao."""

    dossier = models.ForeignKey(ProductDevelopment, on_delete=models.CASCADE, related_name='conditions')
    approval = models.ForeignKey(Approval, on_delete=models.CASCADE, related_name='conditions')
    content = models.CharField(max_length=500, verbose_name='Điều kiện')
    assignee = models.ForeignKey(
        USER, on_delete=models.SET_NULL, null=True, related_name='+', verbose_name='Người xử lý',
    )
    due_at = models.DateTimeField(verbose_name='Hạn hoàn thành')
    done_at = models.DateTimeField(null=True, blank=True)
    done_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    done_note = models.CharField(max_length=500, blank=True, default='', verbose_name='Kết quả xử lý')

    class Meta:
        ordering = ['pk']
        verbose_name = 'Điều kiện duyệt'
        verbose_name_plural = 'Điều kiện duyệt'

    @property
    def is_done(self) -> bool:
        return self.done_at is not None


class Task(models.Model):
    STATE_OPEN = 'open'
    STATE_DONE = 'done'
    STATE_CANCELLED = 'cancelled'
    STATE_CHOICES = [(STATE_OPEN, 'Đang xử lý'), (STATE_DONE, 'Hoàn thành'), (STATE_CANCELLED, 'Đã hủy')]

    dossier = models.ForeignKey(ProductDevelopment, on_delete=models.CASCADE, related_name='tasks')
    step = models.CharField(max_length=30, choices=Status.choices, verbose_name='Bước')
    role = models.CharField(max_length=20, choices=Role.choices, verbose_name='Vai trò')
    title = models.CharField(max_length=255, verbose_name='Công việc')
    is_main = models.BooleanField(default=True, verbose_name='Việc chính của bước')
    assignee = models.ForeignKey(
        USER, on_delete=models.SET_NULL, null=True, blank=True, related_name='tksp_tasks',
        verbose_name='Người phụ trách',
    )
    due_at = models.DateTimeField(null=True, blank=True, verbose_name='Hạn hoàn thành')
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default=STATE_OPEN, db_index=True)
    accepted_at = models.DateTimeField(null=True, blank=True, verbose_name='Nhận việc lúc')
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    delay_reason = models.TextField(blank=True, default='', verbose_name='Nguyên nhân chậm')
    receipt = models.ForeignKey(
        'HandoverReceipt', on_delete=models.CASCADE, null=True, blank=True, related_name='tasks',
    )
    condition = models.ForeignKey(
        ApprovalCondition, on_delete=models.CASCADE, null=True, blank=True, related_name='tasks',
    )
    due_soon_notified_at = models.DateTimeField(null=True, blank=True)
    overdue_notified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['due_at', 'pk']
        verbose_name = 'Công việc'
        verbose_name_plural = 'Công việc'

    def __str__(self):
        return self.title

    @property
    def is_overdue(self) -> bool:
        return self.state == self.STATE_OPEN and bool(self.due_at) and self.due_at < timezone.now()

    @property
    def is_due_soon(self) -> bool:
        if self.state != self.STATE_OPEN or not self.due_at:
            return False
        left = self.due_at - timezone.now()
        return timedelta(0) <= left <= timedelta(hours=48)

    @property
    def days_late(self) -> int:
        if not self.is_overdue:
            return 0
        return max((timezone.localdate() - timezone.localtime(self.due_at).date()).days, 1)


class AttachmentKind(models.TextChoices):
    REFERENCE = 'reference', 'Tham khảo'
    FRONT = 'front', 'Ảnh mặt trước'
    BACK = 'back', 'Ảnh mặt sau'
    DETAIL = 'detail', 'Ảnh chi tiết'
    DESIGN_SOURCE = 'design_source', 'File thiết kế gốc'
    DESIGN_PREVIEW = 'design_preview', 'File xem nhanh'
    COLORWAY = 'colorway', 'Ảnh colorway'
    TECH_SPEC = 'tech_spec', 'Bảng thông số / tài liệu kỹ thuật'
    SAMPLE_PHOTO = 'sample_photo', 'Ảnh mẫu thực tế'
    EVALUATION = 'evaluation', 'Biên bản đánh giá'
    COST = 'cost', 'Bảng giá thành'
    OTHER = 'other', 'Khác'


# Loại tệp chỉ có một bản hiện hành trong cùng phạm vi — tải bản mới thì bản cũ thành lưu trữ.
SINGLE_CURRENT_KINDS = frozenset({
    AttachmentKind.FRONT,
    AttachmentKind.BACK,
    AttachmentKind.DESIGN_SOURCE,
    AttachmentKind.DESIGN_PREVIEW,
    AttachmentKind.TECH_SPEC,
    AttachmentKind.COST,
})
DESIGN_KINDS = (
    AttachmentKind.FRONT,
    AttachmentKind.BACK,
    AttachmentKind.DETAIL,
    AttachmentKind.DESIGN_SOURCE,
    AttachmentKind.DESIGN_PREVIEW,
    AttachmentKind.COLORWAY,
)
SAMPLE_KINDS = (
    AttachmentKind.SAMPLE_PHOTO,
    AttachmentKind.TECH_SPEC,
    AttachmentKind.EVALUATION,
)
DOSSIER_KINDS = (
    AttachmentKind.REFERENCE,
    AttachmentKind.COST,
    AttachmentKind.OTHER,
)
IMAGE_EXTENSIONS = frozenset({'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'})


def attachment_upload_to(instance, filename: str) -> str:
    dossier = getattr(instance, 'dossier', None)
    code = (getattr(dossier, 'code', '') or 'unknown').replace('/', '-')
    safe = get_valid_filename(os.path.basename(filename)) or 'file'
    return f'thiet_ke_sp/{code}/{uuid.uuid4().hex[:12]}_{safe}'


@cleanup.ignore
class Attachment(models.Model):
    """Tệp không bao giờ bị xoá vật lý — xoá chỉ đánh dấu để giữ lịch sử phiên bản."""

    dossier = models.ForeignKey(ProductDevelopment, on_delete=models.CASCADE, related_name='attachments')
    design_version = models.ForeignKey(
        DesignVersion, on_delete=models.CASCADE, null=True, blank=True, related_name='attachments',
    )
    sample_version = models.ForeignKey(
        SampleVersion, on_delete=models.CASCADE, null=True, blank=True, related_name='attachments',
    )
    colorway = models.ForeignKey(Colorway, on_delete=models.SET_NULL, null=True, blank=True, related_name='images')
    kind = models.CharField(max_length=20, choices=AttachmentKind.choices, default=AttachmentKind.OTHER)
    file = models.FileField(
        upload_to=attachment_upload_to, storage=DesignDocNasStorage(), max_length=500, verbose_name='Tệp',
    )
    original_name = models.CharField(max_length=255, blank=True, default='')
    size = models.PositiveBigIntegerField(default=0)
    note = models.CharField(max_length=255, blank=True, default='', verbose_name='Ghi chú')
    is_current = models.BooleanField(default=True, verbose_name='Tệp hiện hành')
    uploaded_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, related_name='+')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-uploaded_at', '-pk']
        verbose_name = 'Tệp đính kèm'
        verbose_name_plural = 'Tệp đính kèm'

    def __str__(self):
        return self.display_name

    @property
    def display_name(self) -> str:
        return self.original_name or (self.file.name or '').rsplit('/', 1)[-1] or f'Tệp #{self.pk}'

    @property
    def is_image(self) -> bool:
        return os.path.splitext(self.display_name)[1].lower() in IMAGE_EXTENSIONS

    @property
    def is_in_current_version(self) -> bool:
        if self.is_deleted or not self.is_current:
            return False
        if self.design_version_id and not self.design_version.is_current:
            return False
        if self.sample_version_id and not self.sample_version.is_current:
            return False
        return True

    def get_absolute_url(self):
        return reverse('thiet_ke_sp:attachment_serve', args=[self.pk])


class Comment(models.Model):
    dossier = models.ForeignKey(ProductDevelopment, on_delete=models.CASCADE, related_name='comments')
    design_version = models.ForeignKey(
        DesignVersion, on_delete=models.SET_NULL, null=True, blank=True, related_name='comments',
    )
    sample_version = models.ForeignKey(
        SampleVersion, on_delete=models.SET_NULL, null=True, blank=True, related_name='comments',
    )
    author = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, related_name='+')
    body = models.TextField(verbose_name='Nội dung')
    is_revision_request = models.BooleanField(default=False, verbose_name='Yêu cầu chỉnh sửa')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        verbose_name = 'Trao đổi'
        verbose_name_plural = 'Trao đổi'


class AuditLog(models.Model):
    dossier = models.ForeignKey(ProductDevelopment, on_delete=models.CASCADE, related_name='audit_logs')
    actor = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, related_name='+')
    action = models.CharField(max_length=50, db_index=True)
    summary = models.TextField()
    from_status = models.CharField(max_length=30, blank=True, default='', choices=Status.choices)
    to_status = models.CharField(max_length=30, blank=True, default='', choices=Status.choices)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        verbose_name = 'Nhật ký xử lý'
        verbose_name_plural = 'Nhật ký xử lý'


class Handover(models.Model):
    dossier = models.OneToOneField(ProductDevelopment, on_delete=models.CASCADE, related_name='handover')
    product_code = models.CharField(max_length=60, verbose_name='Mã sản phẩm chính thức')
    design_version = models.ForeignKey(DesignVersion, on_delete=models.CASCADE, related_name='+')
    sample_version = models.ForeignKey(SampleVersion, on_delete=models.CASCADE, related_name='+')
    tech_doc = models.ForeignKey(
        'san_xuat.ProductTechDoc', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tksp_handovers', verbose_name='Hồ sơ thiết kế SX',
    )
    note = models.TextField(blank=True, default='', verbose_name='Nội dung bàn giao')
    handed_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, related_name='+')
    handed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Bàn giao sản xuất'
        verbose_name_plural = 'Bàn giao sản xuất'


class ReceivingDepartment(models.TextChoices):
    PLANNING = 'planning', 'Kế hoạch'
    PURCHASING = 'purchasing', 'Mua hàng'
    PRODUCTION = 'production', 'Sản xuất'
    QA = 'qa', 'QA/QC'


class HandoverReceipt(models.Model):
    handover = models.ForeignKey(Handover, on_delete=models.CASCADE, related_name='receipts')
    department = models.CharField(max_length=20, choices=ReceivingDepartment.choices)
    receiver = models.ForeignKey(
        USER, on_delete=models.SET_NULL, null=True, related_name='tksp_handover_receipts',
        verbose_name='Người nhận',
    )
    confirmed_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    confirmed_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        ordering = ['pk']
        unique_together = [('handover', 'department')]
        verbose_name = 'Xác nhận nhận bàn giao'
        verbose_name_plural = 'Xác nhận nhận bàn giao'

    @property
    def is_confirmed(self) -> bool:
        return self.confirmed_at is not None


class Notification(models.Model):
    user = models.ForeignKey(USER, on_delete=models.CASCADE, related_name='tksp_notifications')
    dossier = models.ForeignKey(ProductDevelopment, on_delete=models.CASCADE, null=True, blank=True, related_name='+')
    kind = models.CharField(max_length=30, db_index=True)
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, default='')
    url = models.CharField(max_length=500, blank=True, default='')
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        verbose_name = 'Thông báo thiết kế SP'
        verbose_name_plural = 'Thông báo thiết kế SP'


class ModuleSetting(models.Model):
    """Cấu hình một dòng: số ngày chuẩn từng bước, giờ chốt hạn, người nhận bàn giao mặc định."""

    sla_days = models.JSONField(default=dict, blank=True, verbose_name='Số ngày chuẩn theo bước')
    due_hour = models.PositiveSmallIntegerField(default=17, verbose_name='Giờ chốt hạn')
    default_receivers = models.JSONField(default=dict, blank=True, verbose_name='Người nhận bàn giao mặc định')
    updated_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Thiết lập thiết kế sản phẩm'
        verbose_name_plural = 'Thiết lập thiết kế sản phẩm'
