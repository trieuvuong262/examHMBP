import uuid

from django.conf import settings
from django.db import models


class WorkTask(models.Model):
    TYPE_PRODUCTION = 'PRODUCTION'
    TYPE_OFFICE = 'OFFICE'
    TYPE_GENERAL = 'GENERAL'
    TYPE_CHOICES = [
        (TYPE_PRODUCTION, 'Sản xuất'),
        (TYPE_OFFICE, 'Văn phòng'),
        (TYPE_GENERAL, 'Chung'),
    ]

    PRIORITY_LOW = 'LOW'
    PRIORITY_NORMAL = 'NORMAL'
    PRIORITY_HIGH = 'HIGH'
    PRIORITY_URGENT = 'URGENT'
    PRIORITY_CHOICES = [
        (PRIORITY_LOW, 'Thấp'),
        (PRIORITY_NORMAL, 'Bình thường'),
        (PRIORITY_HIGH, 'Cao'),
        (PRIORITY_URGENT, 'Khẩn cấp'),
    ]

    STATUS_PENDING_ACK = 'pending_ack'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_REJECTED = 'rejected'
    STATUS_PENDING_REVIEW = 'pending_review'
    STATUS_REVISION = 'revision'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_REASSIGNED = 'reassigned'
    STATUS_CHOICES = [
        (STATUS_PENDING_ACK, 'Chờ xác nhận'),
        (STATUS_IN_PROGRESS, 'Đang thực hiện'),
        (STATUS_REJECTED, 'Đã từ chối'),
        (STATUS_PENDING_REVIEW, 'Chờ duyệt'),
        (STATUS_REVISION, 'Cần sửa lại'),
        (STATUS_COMPLETED, 'Hoàn thành'),
        (STATUS_CANCELLED, 'Đã hủy'),
        (STATUS_REASSIGNED, 'Đã giao lại'),
    ]

    ACTIVE_ASSIGNEE_STATUSES = {
        STATUS_PENDING_ACK,
        STATUS_IN_PROGRESS,
        STATUS_PENDING_REVIEW,
        STATUS_REVISION,
    }

    assignment_batch = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    title = models.CharField(max_length=200, verbose_name='Tiêu đề')
    description = models.TextField(blank=True, verbose_name='Mô tả')
    task_type = models.CharField(
        max_length=20, choices=TYPE_CHOICES, default=TYPE_GENERAL, verbose_name='Loại việc',
    )
    priority = models.CharField(
        max_length=10, choices=PRIORITY_CHOICES, default=PRIORITY_NORMAL, verbose_name='Ưu tiên',
    )
    assigner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='assigned_work_tasks',
        verbose_name='Người giao',
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_work_tasks',
        verbose_name='Người nhận',
    )
    due_date = models.DateField(null=True, blank=True, verbose_name='Hạn hoàn thành')
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING_ACK, db_index=True,
    )
    progress_percent = models.PositiveSmallIntegerField(default=0, verbose_name='Tiến độ %')
    reject_reason = models.TextField(blank=True, verbose_name='Lý do từ chối')
    result_note = models.TextField(blank=True, verbose_name='Kết quả / báo cáo')
    review_note = models.TextField(blank=True, verbose_name='Ghi chú duyệt')
    order_code = models.CharField(max_length=80, blank=True, verbose_name='Mã đơn/Style')
    product_name = models.CharField(max_length=120, blank=True, verbose_name='Tên SP / hạng mục')
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    reassigned_from = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='reassignments',
        verbose_name='Giao lại từ',
    )
    replaced_by = models.OneToOneField(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='replaces',
        verbose_name='Thay bằng việc',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Công việc'
        verbose_name_plural = 'Công việc'

    def __str__(self):
        return f'{self.title} → {self.assignee}'

    @property
    def is_overdue(self):
        if not self.due_date or self.status == self.STATUS_COMPLETED:
            return False
        from django.utils import timezone
        return self.due_date < timezone.localdate()

    @property
    def status_badge_class(self):
        mapping = {
            self.STATUS_PENDING_ACK: 'bg-warning-subtle text-warning',
            self.STATUS_IN_PROGRESS: 'bg-info-subtle text-info',
            self.STATUS_REJECTED: 'bg-danger-subtle text-danger',
            self.STATUS_PENDING_REVIEW: 'bg-primary-subtle text-primary',
            self.STATUS_REVISION: 'bg-warning-subtle text-warning-emphasis',
            self.STATUS_COMPLETED: 'bg-success-subtle text-success',
            self.STATUS_CANCELLED: 'bg-secondary-subtle text-secondary',
            self.STATUS_REASSIGNED: 'bg-secondary-subtle text-secondary',
        }
        return mapping.get(self.status, 'bg-secondary-subtle text-secondary')


class WorkTaskLog(models.Model):
    ACTION_ASSIGNED = 'assigned'
    ACTION_ACK = 'acknowledged'
    ACTION_REJECT = 'rejected'
    ACTION_PROGRESS = 'progress'
    ACTION_SUBMIT = 'submitted'
    ACTION_APPROVE = 'approved'
    ACTION_REVISION = 'revision'
    ACTION_REASSIGN = 'reassigned'
    ACTION_CANCEL = 'cancelled'
    ACTION_CHOICES = [
        (ACTION_ASSIGNED, 'Giao việc'),
        (ACTION_ACK, 'Xác nhận'),
        (ACTION_REJECT, 'Từ chối'),
        (ACTION_PROGRESS, 'Cập nhật tiến độ'),
        (ACTION_SUBMIT, 'Nộp hoàn thành'),
        (ACTION_APPROVE, 'Duyệt'),
        (ACTION_REVISION, 'Yêu cầu sửa'),
        (ACTION_REASSIGN, 'Giao lại'),
        (ACTION_CANCEL, 'Hủy'),
    ]

    task = models.ForeignKey(WorkTask, on_delete=models.CASCADE, related_name='logs')
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='work_task_logs',
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Nhật ký công việc'
        verbose_name_plural = 'Nhật ký công việc'

    def __str__(self):
        return f'{self.task_id} · {self.get_action_display()}'
