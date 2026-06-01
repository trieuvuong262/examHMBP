import os
import uuid

from django.conf import settings
from django.db import models


class RequestType(models.Model):
    CODE_ASSET_PURCHASE = 'asset_purchase'

    code = models.CharField(max_length=50, unique=True, verbose_name='Mã loại')
    name = models.CharField(max_length=200, verbose_name='Tên loại')
    description = models.TextField(blank=True, verbose_name='Mô tả')
    is_active = models.BooleanField(default=True, verbose_name='Đang dùng')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Thứ tự')

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'Loại yêu cầu'
        verbose_name_plural = 'Loại yêu cầu'

    def __str__(self):
        return self.name


class RequestTypeStepTemplate(models.Model):
    KIND_APPROVAL = 'approval'
    KIND_EXECUTION = 'execution'
    KIND_CHOICES = [
        (KIND_APPROVAL, 'Duyệt'),
        (KIND_EXECUTION, 'Thực hiện'),
    ]

    RULE_DIRECT_MANAGER = 'direct_manager'
    RULE_DEPARTMENT_QUEUE = 'department_queue'
    RULE_DIRECTOR = 'director'
    RULE_CHOICES = [
        (RULE_DIRECT_MANAGER, 'Cấp trên trực tiếp'),
        (RULE_DEPARTMENT_QUEUE, 'Hàng đợi phòng ban'),
        (RULE_DIRECTOR, 'Giám đốc'),
    ]

    request_type = models.ForeignKey(
        RequestType,
        on_delete=models.CASCADE,
        related_name='step_templates',
        verbose_name='Loại yêu cầu',
    )
    step_order = models.PositiveIntegerField(verbose_name='Thứ tự bước')
    name = models.CharField(max_length=200, verbose_name='Tên bước')
    step_kind = models.CharField(
        max_length=20, choices=KIND_CHOICES, default=KIND_APPROVAL, verbose_name='Loại bước',
    )
    assignee_rule = models.CharField(
        max_length=30, choices=RULE_CHOICES, verbose_name='Quy tắc gán người xử lý',
    )
    target_department = models.ForeignKey(
        'hrm.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='request_step_templates',
        verbose_name='Phòng ban xử lý',
    )

    class Meta:
        ordering = ['step_order']
        verbose_name = 'Bước quy trình mẫu'
        verbose_name_plural = 'Bước quy trình mẫu'
        unique_together = ('request_type', 'step_order')

    def __str__(self):
        return f'{self.request_type.name} · #{self.step_order} {self.name}'


class RecurringItemCatalog(models.Model):
    """Danh mục hàng mua định kỳ — quản lý bởi Thu mua."""

    name = models.CharField(max_length=200, verbose_name='Tên hàng')
    description = models.TextField(blank=True, verbose_name='Mô tả')
    unit = models.CharField(max_length=50, default='cái', verbose_name='Đơn vị')
    is_active = models.BooleanField(default=True, verbose_name='Đang dùng')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recurring_catalog_items',
        verbose_name='Người tạo',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Hàng mua định kỳ'
        verbose_name_plural = 'Danh mục hàng mua định kỳ'

    def __str__(self):
        return self.name


class ServiceRequest(models.Model):
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_COMPLETED = 'completed'
    STATUS_REJECTED = 'rejected'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_IN_PROGRESS, 'Đang xử lý'),
        (STATUS_COMPLETED, 'Hoàn thành'),
        (STATUS_REJECTED, 'Từ chối'),
        (STATUS_CANCELLED, 'Đã hủy'),
    ]

    TIER_NONE = 'none'
    TIER_ACCOUNTANT = 'accountant'
    TIER_DIRECTOR = 'director'
    APPROVAL_TIER_CHOICES = [
        (TIER_NONE, 'Không cần duyệt cấp cao'),
        (TIER_ACCOUNTANT, 'Kế toán'),
        (TIER_DIRECTOR, 'Giám đốc'),
    ]

    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='service_requests',
        verbose_name='Người gửi',
    )
    request_type = models.ForeignKey(
        RequestType,
        on_delete=models.PROTECT,
        related_name='requests',
        verbose_name='Loại yêu cầu',
    )
    title = models.CharField(max_length=200, verbose_name='Tiêu đề')
    description = models.TextField(verbose_name='Nội dung')
    estimated_cost = models.DecimalField(
        max_digits=14, decimal_places=0, null=True, blank=True, verbose_name='Dự toán (VNĐ)',
    )
    recurring_item = models.ForeignKey(
        RecurringItemCatalog,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='requests',
        verbose_name='Hàng định kỳ',
    )
    is_from_catalog = models.BooleanField(default=False, verbose_name='Từ danh mục định kỳ')
    needs_advance = models.BooleanField(default=False, verbose_name='Cần tạm ứng')
    advance_amount = models.DecimalField(
        max_digits=14, decimal_places=0, null=True, blank=True, verbose_name='Số tiền tạm ứng',
    )
    selected_total_amount = models.DecimalField(
        max_digits=14, decimal_places=0, null=True, blank=True, verbose_name='Tổng NCC đã chọn',
    )
    approval_tier = models.CharField(
        max_length=20, choices=APPROVAL_TIER_CHOICES, blank=True, verbose_name='Cấp duyệt chi phí',
    )
    goods_receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='received_service_requests',
        verbose_name='Người nhận hàng',
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_IN_PROGRESS, db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Yêu cầu nội bộ'
        verbose_name_plural = 'Yêu cầu nội bộ'

    def __str__(self):
        return self.title

    @property
    def is_open(self):
        return self.status == self.STATUS_IN_PROGRESS

    @property
    def current_step(self):
        return self.steps.filter(
            status__in={
                ServiceRequestStep.STATUS_PENDING,
                ServiceRequestStep.STATUS_IN_PROGRESS,
            },
        ).order_by('step_order').first()


class ProcurementLineItem(models.Model):
    request = models.ForeignKey(
        ServiceRequest,
        on_delete=models.CASCADE,
        related_name='line_items',
        verbose_name='Yêu cầu',
    )
    recurring_item = models.ForeignKey(
        RecurringItemCatalog,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='line_items',
        verbose_name='Hàng định kỳ',
    )
    description = models.CharField(max_length=500, verbose_name='Mô tả hàng hóa')
    quantity_requested = models.DecimalField(
        max_digits=12, decimal_places=2, default=1, verbose_name='SL đề xuất',
    )
    quantity_confirmed = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, verbose_name='SL xác nhận',
    )
    unit = models.CharField(max_length=50, default='cái', verbose_name='Đơn vị')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Thứ tự')

    class Meta:
        ordering = ['sort_order', 'pk']
        verbose_name = 'Dòng hàng mua'
        verbose_name_plural = 'Dòng hàng mua'

    def __str__(self):
        return self.description

    @property
    def effective_quantity(self):
        if self.quantity_confirmed is not None:
            return self.quantity_confirmed
        return self.quantity_requested

    @property
    def selected_quote(self):
        return self.quotes.filter(is_selected=True).first()

    @property
    def line_total(self):
        quote = self.selected_quote
        if not quote:
            return None
        return quote.unit_price * self.effective_quantity


class ProcurementSupplierQuote(models.Model):
    line_item = models.ForeignKey(
        ProcurementLineItem,
        on_delete=models.CASCADE,
        related_name='quotes',
        verbose_name='Dòng hàng',
    )
    supplier_name = models.CharField(max_length=200, verbose_name='Nhà cung cấp')
    unit_price = models.DecimalField(max_digits=14, decimal_places=0, verbose_name='Đơn giá (VNĐ)')
    quote_file = models.FileField(
        upload_to='service_requests/quotes/%Y/%m/',
        blank=True,
        verbose_name='File báo giá',
    )
    is_selected = models.BooleanField(default=False, verbose_name='Được chọn')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['pk']
        verbose_name = 'Báo giá NCC'
        verbose_name_plural = 'Báo giá NCC'

    def __str__(self):
        return f'{self.supplier_name} — {self.line_item_id}'

    @property
    def line_total(self):
        return self.unit_price * self.line_item.effective_quantity


class ServiceRequestStep(models.Model):
    STATUS_BLOCKED = 'blocked'
    STATUS_PENDING = 'pending'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_COMPLETED = 'completed'
    STATUS_REJECTED = 'rejected'
    STATUS_SKIPPED = 'skipped'
    STATUS_CHOICES = [
        (STATUS_BLOCKED, 'Chờ bước trước'),
        (STATUS_PENDING, 'Chờ xử lý'),
        (STATUS_IN_PROGRESS, 'Đang xử lý'),
        (STATUS_COMPLETED, 'Hoàn thành'),
        (STATUS_REJECTED, 'Từ chối'),
        (STATUS_SKIPPED, 'Bỏ qua'),
    ]

    OPEN_HANDLER_STATUSES = {
        STATUS_PENDING,
        STATUS_IN_PROGRESS,
    }

    TERMINAL_STATUSES = {
        STATUS_COMPLETED,
        STATUS_SKIPPED,
        STATUS_REJECTED,
    }

    STEP_TEAM_LEADER = 'team_leader_approval'
    STEP_DIVISION_HEAD = 'division_head_approval'
    STEP_PROCUREMENT_QUOTE = 'procurement_quote'
    STEP_ACCOUNTANT = 'accountant_approval'
    STEP_DIRECTOR = 'director_approval'
    STEP_ADVANCE = 'advance_payment'
    STEP_PURCHASE = 'procurement_purchase'
    STEP_RECEIPT = 'goods_receipt'

    request = models.ForeignKey(
        ServiceRequest,
        on_delete=models.CASCADE,
        related_name='steps',
        verbose_name='Yêu cầu',
    )
    template = models.ForeignKey(
        RequestTypeStepTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='instances',
        verbose_name='Mẫu bước',
    )
    step_order = models.PositiveIntegerField(verbose_name='Thứ tự')
    step_code = models.CharField(max_length=40, blank=True, db_index=True, verbose_name='Mã bước')
    name = models.CharField(max_length=200, verbose_name='Tên bước')
    step_kind = models.CharField(max_length=20, verbose_name='Loại bước')
    assignee_rule = models.CharField(max_length=30, verbose_name='Quy tắc gán')
    target_department = models.ForeignKey(
        'hrm.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='service_request_steps',
        verbose_name='Phòng ban',
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='service_request_steps',
        verbose_name='Người xử lý',
    )
    depends_on = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='dependent_steps',
        verbose_name='Phụ thuộc bước',
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_BLOCKED, db_index=True,
    )
    note = models.TextField(blank=True, verbose_name='Ghi chú / kết quả')
    due_date = models.DateField(null=True, blank=True, verbose_name='Hạn xử lý')
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['step_order']
        verbose_name = 'Bước yêu cầu'
        verbose_name_plural = 'Bước yêu cầu'

    def __str__(self):
        return f'{self.request_id} · #{self.step_order} {self.name}'

    @property
    def is_approval(self):
        return self.step_kind == RequestTypeStepTemplate.KIND_APPROVAL

    @property
    def is_execution(self):
        return self.step_kind == RequestTypeStepTemplate.KIND_EXECUTION

    @property
    def status_badge_class(self):
        mapping = {
            self.STATUS_BLOCKED: 'bg-secondary',
            self.STATUS_PENDING: 'bg-warning text-dark',
            self.STATUS_IN_PROGRESS: 'bg-info text-dark',
            self.STATUS_COMPLETED: 'bg-success',
            self.STATUS_REJECTED: 'bg-danger',
            self.STATUS_SKIPPED: 'bg-secondary',
        }
        return mapping.get(self.status, 'bg-light text-dark border')


class ServiceRequestAttachment(models.Model):
    STAGE_REQUEST = 'request'
    STAGE_RESULT = 'result'
    STAGE_CHOICES = [
        (STAGE_REQUEST, 'Khi gửi'),
        (STAGE_RESULT, 'Kết quả xử lý'),
    ]

    request = models.ForeignKey(
        ServiceRequest,
        on_delete=models.CASCADE,
        related_name='attachments',
    )
    step = models.ForeignKey(
        ServiceRequestStep,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='attachments',
    )
    file = models.FileField(upload_to='service_requests/%Y/%m/')
    original_name = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='service_request_uploads',
    )
    stage = models.CharField(max_length=10, choices=STAGE_CHOICES, default=STAGE_REQUEST)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    @property
    def display_name(self):
        if self.original_name:
            return self.original_name
        return os.path.basename(self.file.name)

    @property
    def is_image(self):
        from tasks.attachment_utils import is_image_filename
        return is_image_filename(self.display_name)


class ServiceRequestLog(models.Model):
    request = models.ForeignKey(
        ServiceRequest,
        on_delete=models.CASCADE,
        related_name='logs',
    )
    step = models.ForeignKey(
        ServiceRequestStep,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='logs',
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='service_request_logs',
    )
    action = models.CharField(max_length=30)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
