from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

USER = settings.AUTH_USER_MODEL


class Status(models.TextChoices):
    DRAFT = 'draft', 'Nháp'
    PLAN_PENDING = 'plan_pending', 'Chờ duyệt kế hoạch'
    PREPARING = 'preparing', 'Đang chuẩn bị'
    AT_RISK = 'at_risk', 'Có rủi ro'
    LAUNCH_PENDING = 'launch_pending', 'Chờ duyệt ra mắt'
    READY = 'ready', 'Đủ điều kiện ra mắt'
    LAUNCHED = 'launched', 'Đã ra mắt'
    REVIEWING = 'reviewing', 'Đang đánh giá sau ra mắt'
    DONE = 'done', 'Hoàn tất'
    PAUSED = 'paused', 'Tạm dừng'
    CANCELLED = 'cancelled', 'Đã hủy'


FINAL_STATUSES = (Status.DONE, Status.CANCELLED)
PREPARING_STATUSES = (Status.PREPARING, Status.AT_RISK)
EDITABLE_STATUSES = (Status.DRAFT, Status.PLAN_PENDING, Status.PREPARING, Status.AT_RISK)
APPROVAL_STATUSES = (Status.PLAN_PENDING, Status.LAUNCH_PENDING)

STATUS_TONES = {
    Status.DRAFT: 'gray',
    Status.PLAN_PENDING: 'purple',
    Status.PREPARING: 'blue',
    Status.AT_RISK: 'red',
    Status.LAUNCH_PENDING: 'purple',
    Status.READY: 'green',
    Status.LAUNCHED: 'green',
    Status.REVIEWING: 'blue',
    Status.DONE: 'dark',
    Status.PAUSED: 'gray',
    Status.CANCELLED: 'gray',
}


class TaskGroup(models.TextChoices):
    PRODUCT = 'product', 'Sản phẩm & kỹ thuật'
    PRODUCTION = 'production', 'Sản xuất & cung ứng'
    PRICE = 'price', 'Giá & kinh doanh'
    MARKETING = 'marketing', 'Marketing'
    CHANNEL = 'channel', 'Kênh bán hàng'
    LOGISTICS = 'logistics', 'Kho vận'
    APPROVAL = 'approval', 'Phê duyệt & điều kiện'


# Trọng số nhóm khi tính % sẵn sàng ra mắt (tổng 100).
GROUP_WEIGHTS = {
    TaskGroup.PRODUCT: 20,
    TaskGroup.PRODUCTION: 25,
    TaskGroup.PRICE: 15,
    TaskGroup.MARKETING: 20,
    TaskGroup.CHANNEL: 10,
    TaskGroup.LOGISTICS: 10,
}

# Tab chi tiết tương ứng từng nhóm công việc.
GROUP_PAGES = {
    TaskGroup.PRODUCT: 'products',
    TaskGroup.PRODUCTION: 'production',
    TaskGroup.PRICE: 'sales',
    TaskGroup.MARKETING: 'marketing',
    TaskGroup.CHANNEL: 'sales',
    TaskGroup.LOGISTICS: 'production',
    TaskGroup.APPROVAL: 'go',
}


class Importance(models.TextChoices):
    HIGH = 'high', 'Quan trọng'
    NORMAL = 'normal', 'Bình thường'


class TaskStatus(models.TextChoices):
    TODO = 'todo', 'Chưa làm'
    DOING = 'doing', 'Đang làm'
    BLOCKED = 'blocked', 'Vướng mắc'
    DONE = 'done', 'Hoàn thành'
    NA = 'na', 'Không áp dụng'


OPEN_TASK_STATUSES = (TaskStatus.TODO, TaskStatus.DOING, TaskStatus.BLOCKED)
CLOSED_TASK_STATUSES = (TaskStatus.DONE, TaskStatus.NA)


def milestone_label(offset_days: int) -> str:
    if offset_days == 0:
        return 'D-Day'
    if offset_days < 0:
        return f'T{offset_days}'
    return f'D+{offset_days}'


class LaunchSequence(models.Model):
    """Bộ đếm mã kế hoạch theo năm (LRM-YYYY-NNNN)."""

    year = models.PositiveIntegerField(primary_key=True)
    last_no = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'ra_mat_sp_sequence'


class LaunchPlan(models.Model):
    code = models.CharField(max_length=20, unique=True, verbose_name='Mã kế hoạch')
    name = models.CharField(max_length=255, verbose_name='Tên kế hoạch / đợt ra mắt')
    launch_date = models.DateField(verbose_name='Ngày ra mắt dự kiến')
    coordinator = models.ForeignKey(
        USER, on_delete=models.PROTECT, related_name='ra_mat_coordinated', verbose_name='Người điều phối',
    )
    approver = models.ForeignKey(
        USER, on_delete=models.SET_NULL, null=True, blank=True, related_name='ra_mat_approving',
        verbose_name='Người duyệt (Go/No-Go)',
    )
    scope = models.CharField(max_length=255, blank=True, default='', verbose_name='Phạm vi ra mắt')
    channels = models.CharField(max_length=255, blank=True, default='', verbose_name='Kênh bán')
    objective = models.TextField(blank=True, default='', verbose_name='Mục tiêu ra mắt')
    target_customer = models.CharField(max_length=255, blank=True, default='', verbose_name='Khách hàng mục tiêu')
    positioning = models.TextField(blank=True, default='', verbose_name='Định vị / thông điệp chính')
    target_qty = models.PositiveIntegerField(null=True, blank=True, verbose_name='Mục tiêu sản lượng bán')
    target_revenue = models.DecimalField(
        max_digits=16, decimal_places=0, null=True, blank=True, verbose_name='Mục tiêu doanh thu (đ)',
    )
    marketing_budget = models.DecimalField(
        max_digits=16, decimal_places=0, null=True, blank=True, verbose_name='Ngân sách marketing (đ)',
    )
    note = models.TextField(blank=True, default='', verbose_name='Ghi chú')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    status_changed_at = models.DateTimeField(default=timezone.now)
    paused_from_status = models.CharField(max_length=20, blank=True, default='', choices=Status.choices)
    launched_at = models.DateTimeField(null=True, blank=True, verbose_name='Ra mắt thực tế lúc')
    created_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ra_mat_sp_plan'
        ordering = ['launch_date', 'pk']
        verbose_name = 'Kế hoạch ra mắt'
        verbose_name_plural = 'Kế hoạch ra mắt'

    def __str__(self):
        return f'{self.code} — {self.name}'

    def get_absolute_url(self):
        return reverse('ra_mat_sp:detail', args=[self.pk])

    @property
    def status_tone(self) -> str:
        return STATUS_TONES.get(self.status, 'gray')

    @property
    def is_final(self) -> bool:
        return self.status in FINAL_STATUSES

    @property
    def days_to_launch(self) -> int:
        return (self.launch_date - timezone.localdate()).days

    @property
    def countdown_label(self) -> str:
        days = self.days_to_launch
        if days > 0:
            return f'Còn {days} ngày'
        if days == 0:
            return 'Hôm nay ra mắt'
        return f'Đã qua {-days} ngày'


class LaunchPlanProduct(models.Model):
    plan = models.ForeignKey(LaunchPlan, on_delete=models.CASCADE, related_name='products')
    dossier = models.ForeignKey(
        'thiet_ke_sp.ProductDevelopment', on_delete=models.CASCADE, related_name='launch_links',
        verbose_name='Hồ sơ thiết kế',
    )
    planned_qty = models.PositiveIntegerField(null=True, blank=True, verbose_name='Sản lượng ra mắt')
    note = models.CharField(max_length=255, blank=True, default='', verbose_name='Ghi chú')
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'ra_mat_sp_plan_product'
        ordering = ['sort_order', 'pk']
        constraints = [
            models.UniqueConstraint(fields=['plan', 'dossier'], name='ra_mat_sp_plan_dossier_uniq'),
        ]


class LaunchGroupDefault(models.Model):
    """Người chịu trách nhiệm mặc định của một nhóm — áp cho kế hoạch tạo mới."""

    group = models.CharField(max_length=20, choices=TaskGroup.choices, unique=True, verbose_name='Nhóm')
    owner = models.ForeignKey(
        USER, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
        verbose_name='Người chịu trách nhiệm',
    )

    class Meta:
        db_table = 'ra_mat_sp_group_default'
        verbose_name = 'Phụ trách nhóm mặc định'
        verbose_name_plural = 'Phụ trách nhóm mặc định'


class LaunchPlanGroupOwner(models.Model):
    """Người chịu trách nhiệm chính của một nhóm trên một kế hoạch."""

    plan = models.ForeignKey(LaunchPlan, on_delete=models.CASCADE, related_name='group_owners')
    group = models.CharField(max_length=20, choices=TaskGroup.choices, verbose_name='Nhóm')
    owner = models.ForeignKey(
        USER, on_delete=models.SET_NULL, null=True, blank=True, related_name='ra_mat_group_owned',
        verbose_name='Người chịu trách nhiệm',
    )

    class Meta:
        db_table = 'ra_mat_sp_plan_group_owner'
        constraints = [
            models.UniqueConstraint(fields=['plan', 'group'], name='ra_mat_sp_plan_group_owner_uniq'),
        ]
        verbose_name = 'Phụ trách nhóm trên kế hoạch'
        verbose_name_plural = 'Phụ trách nhóm trên kế hoạch'


class ChecklistTemplateItem(models.Model):
    """Dòng checklist mẫu — sinh công việc khi tạo kế hoạch (hạn = ngày ra mắt + offset)."""

    group = models.CharField(max_length=20, choices=TaskGroup.choices, verbose_name='Nhóm')
    offset_days = models.IntegerField(verbose_name='Mốc (ngày so với D-Day)', help_text='-90 = T-90, 0 = D-Day, 7 = D+7')
    title = models.CharField(max_length=255, verbose_name='Công việc')
    deliverable = models.CharField(max_length=255, blank=True, default='', verbose_name='Kết quả cần có')
    importance = models.CharField(max_length=10, choices=Importance.choices, default=Importance.NORMAL)
    is_go_blocker = models.BooleanField(default=False, verbose_name='Điều kiện bắt buộc Go/No-Go')
    product_group = models.CharField(
        max_length=32, blank=True, default='', verbose_name='Chỉ áp dụng cho nhóm SP',
        help_text='Để trống = áp dụng mọi nhóm sản phẩm.',
    )
    sort_order = models.PositiveIntegerField(default=100)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = 'ra_mat_sp_template_item'
        ordering = ['offset_days', 'sort_order', 'pk']
        verbose_name = 'Checklist mẫu'
        verbose_name_plural = 'Checklist mẫu'

    def __str__(self):
        return f'{milestone_label(self.offset_days)} · {self.title}'

    @property
    def milestone(self) -> str:
        return milestone_label(self.offset_days)


class LaunchTask(models.Model):
    plan = models.ForeignKey(LaunchPlan, on_delete=models.CASCADE, related_name='tasks')
    template_item = models.ForeignKey(
        ChecklistTemplateItem, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    group = models.CharField(max_length=20, choices=TaskGroup.choices, verbose_name='Nhóm')
    offset_days = models.IntegerField(verbose_name='Mốc')
    title = models.CharField(max_length=255, verbose_name='Công việc')
    deliverable = models.CharField(max_length=255, blank=True, default='', verbose_name='Kết quả cần có')
    importance = models.CharField(max_length=10, choices=Importance.choices, default=Importance.NORMAL)
    is_go_blocker = models.BooleanField(default=False, verbose_name='Điều kiện Go/No-Go')
    owner = models.ForeignKey(
        USER, on_delete=models.SET_NULL, null=True, blank=True, related_name='ra_mat_tasks',
        verbose_name='Người phụ trách',
    )
    collaborators = models.ManyToManyField(
        USER, blank=True, related_name='ra_mat_collab_tasks', verbose_name='Người phối hợp',
    )
    start_date = models.DateField(null=True, blank=True, verbose_name='Ngày bắt đầu')
    due_date = models.DateField(verbose_name='Hạn hoàn thành')
    status = models.CharField(max_length=10, choices=TaskStatus.choices, default=TaskStatus.TODO, db_index=True)
    evidence = models.TextField(blank=True, default='', verbose_name='Bằng chứng / kết quả')
    delay_reason = models.TextField(blank=True, default='', verbose_name='Lý do trễ / vướng mắc')
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    is_condition = models.BooleanField(default=False, verbose_name='Điều kiện từ quyết định ra mắt')
    sort_order = models.PositiveIntegerField(default=100)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ra_mat_sp_task'
        ordering = ['offset_days', 'sort_order', 'pk']
        indexes = [models.Index(fields=['owner', 'status'])]

    def __str__(self):
        return self.title

    @property
    def milestone(self) -> str:
        return milestone_label(self.offset_days)

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_TASK_STATUSES

    @property
    def status_tone(self) -> str:
        if self.is_overdue:
            return 'red'
        return {
            TaskStatus.DOING: 'blue', TaskStatus.BLOCKED: 'amber', TaskStatus.DONE: 'green',
        }.get(self.status, 'gray')

    @property
    def is_overdue(self) -> bool:
        return self.is_open and self.due_date < timezone.localdate()

    @property
    def weight(self) -> int:
        base = 3 if self.importance == Importance.HIGH else 1
        return base * 2 if self.is_go_blocker else base

    def recompute_due(self, launch_date) -> None:
        self.due_date = launch_date + timedelta(days=self.offset_days)


def task_file_upload_to(instance, filename: str) -> str:
    import os
    import uuid

    ext = os.path.splitext(filename)[1].lower()[:10]
    now = timezone.now()
    return f'ra_mat_sp/evidence/{now:%Y/%m}/{uuid.uuid4().hex}{ext}'


class LaunchTaskFile(models.Model):
    """Tệp bằng chứng hoàn thành công việc."""

    task = models.ForeignKey(LaunchTask, on_delete=models.CASCADE, related_name='files')
    file = models.FileField(upload_to=task_file_upload_to, max_length=500, verbose_name='Tệp')
    original_name = models.CharField(max_length=255, blank=True, default='')
    size = models.PositiveBigIntegerField(default=0)
    uploaded_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, related_name='+')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ra_mat_sp_task_file'
        ordering = ['uploaded_at', 'pk']
        verbose_name = 'Tệp bằng chứng'
        verbose_name_plural = 'Tệp bằng chứng'

    def __str__(self):
        return self.display_name

    @property
    def display_name(self) -> str:
        return self.original_name or (self.file.name or '').rsplit('/', 1)[-1]

    def get_absolute_url(self):
        return reverse('ra_mat_sp:task_file', args=[self.pk])


class RiskSeverity(models.TextChoices):
    HIGH = 'high', 'Cao'
    MEDIUM = 'medium', 'Trung bình'
    LOW = 'low', 'Thấp'


class LaunchRisk(models.Model):
    STATE_OPEN = 'open'
    STATE_RESOLVED = 'resolved'
    STATE_CHOICES = [(STATE_OPEN, 'Đang mở'), (STATE_RESOLVED, 'Đã xử lý')]

    plan = models.ForeignKey(LaunchPlan, on_delete=models.CASCADE, related_name='risks')
    group = models.CharField(max_length=20, choices=TaskGroup.choices, verbose_name='Nhóm')
    severity = models.CharField(max_length=10, choices=RiskSeverity.choices, default=RiskSeverity.MEDIUM, verbose_name='Mức độ')
    description = models.TextField(verbose_name='Rủi ro / vướng mắc')
    action = models.TextField(blank=True, default='', verbose_name='Hướng xử lý')
    owner = models.ForeignKey(
        USER, on_delete=models.SET_NULL, null=True, blank=True, related_name='ra_mat_risks', verbose_name='Người xử lý',
    )
    due_date = models.DateField(null=True, blank=True, verbose_name='Hạn xử lý')
    state = models.CharField(max_length=10, choices=STATE_CHOICES, default=STATE_OPEN, db_index=True)
    resolution = models.TextField(blank=True, default='', verbose_name='Kết quả xử lý')
    created_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'ra_mat_sp_risk'
        ordering = ['state', '-created_at']

    @property
    def is_open(self) -> bool:
        return self.state == self.STATE_OPEN


class DecisionKind(models.TextChoices):
    PLAN = 'plan', 'Duyệt kế hoạch'
    GO = 'go', 'Duyệt ra mắt (Go/No-Go)'
    STOP = 'stop', 'Tạm dừng / Tiếp tục / Hủy'


class Decision(models.TextChoices):
    APPROVED = 'approved', 'Duyệt'
    REQUEST_CHANGE = 'request_change', 'Yêu cầu chỉnh sửa'
    GO = 'go', 'Đủ điều kiện ra mắt'
    GO_CONDITIONAL = 'go_conditional', 'Ra mắt có điều kiện'
    POSTPONE = 'postpone', 'Dời ngày ra mắt'
    PAUSED = 'paused', 'Tạm dừng'
    RESUMED = 'resumed', 'Tiếp tục'
    CANCELLED = 'cancelled', 'Hủy'


GO_DECISIONS = (Decision.GO, Decision.GO_CONDITIONAL, Decision.POSTPONE, Decision.PAUSED, Decision.CANCELLED)
PLAN_DECISIONS = (Decision.APPROVED, Decision.REQUEST_CHANGE, Decision.CANCELLED)


class LaunchDecision(models.Model):
    plan = models.ForeignKey(LaunchPlan, on_delete=models.CASCADE, related_name='decisions')
    kind = models.CharField(max_length=10, choices=DecisionKind.choices)
    decision = models.CharField(max_length=20, choices=Decision.choices)
    comment = models.TextField(blank=True, default='', verbose_name='Ý kiến')
    readiness = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='% sẵn sàng lúc quyết định')
    new_launch_date = models.DateField(null=True, blank=True, verbose_name='Ngày ra mắt mới')
    condition_text = models.CharField(max_length=500, blank=True, default='', verbose_name='Điều kiện')
    condition_owner = models.ForeignKey(
        USER, on_delete=models.SET_NULL, null=True, blank=True, related_name='+', verbose_name='Người xử lý điều kiện',
    )
    condition_due = models.DateField(null=True, blank=True, verbose_name='Hạn xử lý điều kiện')
    decided_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, related_name='+')
    decided_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'ra_mat_sp_decision'
        ordering = ['-decided_at', '-pk']


class ReviewMilestone(models.TextChoices):
    D1 = 'd1', 'D+1'
    D7 = 'd7', 'D+7'
    D30 = 'd30', 'D+30'


REVIEW_OFFSETS = {ReviewMilestone.D1: 1, ReviewMilestone.D7: 7, ReviewMilestone.D30: 30}


class ReviewDecision(models.TextChoices):
    CONTINUE = 'continue', 'Duy trì bán'
    REORDER = 'reorder', 'Tái sản xuất / nhập thêm'
    PUSH = 'push', 'Đẩy mạnh truyền thông'
    ADJUST = 'adjust', 'Điều chỉnh giá / sản phẩm'
    CLEARANCE = 'clearance', 'Xả hàng / dừng bán'


class PostLaunchReview(models.Model):
    plan = models.ForeignKey(LaunchPlan, on_delete=models.CASCADE, related_name='reviews')
    milestone = models.CharField(max_length=4, choices=ReviewMilestone.choices)
    due_date = models.DateField(verbose_name='Ngày đánh giá')
    qty_sold = models.PositiveIntegerField(null=True, blank=True, verbose_name='Sản lượng đã bán')
    revenue = models.DecimalField(max_digits=16, decimal_places=0, null=True, blank=True, verbose_name='Doanh thu (đ)')
    stock_left = models.PositiveIntegerField(null=True, blank=True, verbose_name='Tồn còn lại')
    return_rate = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, verbose_name='Tỷ lệ đổi trả (%)',
    )
    feedback = models.TextField(blank=True, default='', verbose_name='Phản hồi khách hàng / kênh')
    findings = models.TextField(blank=True, default='', verbose_name='Nhận định / bài học')
    decision = models.CharField(
        max_length=20, choices=ReviewDecision.choices, blank=True, default='', verbose_name='Quyết định tiếp theo',
    )
    submitted_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'ra_mat_sp_review'
        ordering = ['due_date']
        constraints = [
            models.UniqueConstraint(fields=['plan', 'milestone'], name='ra_mat_sp_review_uniq'),
        ]

    @property
    def is_done(self) -> bool:
        return self.submitted_at is not None

    @property
    def revenue_pct(self) -> int | None:
        target = self.plan.target_revenue
        if not target or self.revenue is None:
            return None
        return round(float(self.revenue) * 100 / float(target))

    @property
    def qty_pct(self) -> int | None:
        target = self.plan.target_qty
        if not target or self.qty_sold is None:
            return None
        return round(self.qty_sold * 100 / target)


class AuditLog(models.Model):
    plan = models.ForeignKey(LaunchPlan, on_delete=models.CASCADE, related_name='logs')
    user = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, related_name='+')
    action = models.CharField(max_length=40)
    message = models.TextField()
    is_status = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ra_mat_sp_log'
        ordering = ['-created_at', '-pk']
