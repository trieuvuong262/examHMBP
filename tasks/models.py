import os

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
    STATUS_BLOCKED = 'blocked'
    STATUS_HANDED_OFF = 'handed_off'
    STATUS_CHOICES = [
        (STATUS_PENDING_ACK, 'Chờ xác nhận'),
        (STATUS_IN_PROGRESS, 'Đang thực hiện'),
        (STATUS_REJECTED, 'Đã từ chối'),
        (STATUS_PENDING_REVIEW, 'Chờ duyệt'),
        (STATUS_REVISION, 'Cần sửa lại'),
        (STATUS_COMPLETED, 'Hoàn thành'),
        (STATUS_CANCELLED, 'Đã hủy'),
        (STATUS_REASSIGNED, 'Đã giao lại'),
        (STATUS_BLOCKED, 'Chờ bước trước'),
        (STATUS_HANDED_OFF, 'Đã chuyển giao'),
    ]

    ACTIVE_ASSIGNEE_STATUSES = {
        STATUS_PENDING_ACK,
        STATUS_IN_PROGRESS,
        STATUS_PENDING_REVIEW,
        STATUS_REVISION,
    }

    # Việc assignee còn phải theo dõi / xử lý — nhắc trang chủ đến khi hoàn thành
    OPEN_ASSIGNEE_STATUSES = {
        STATUS_PENDING_ACK,
        STATUS_IN_PROGRESS,
        STATUS_PENDING_REVIEW,
        STATUS_REVISION,
        STATUS_BLOCKED,
    }

    # Việc cấp trên / chủ dự án cần hành động
    MANAGER_ACTION_STATUSES = {
        STATUS_PENDING_REVIEW,
        STATUS_REJECTED,
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
    project = models.ForeignKey(
        'InternalProject',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='steps',
        verbose_name='Dự án',
    )
    depends_on = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='dependent_steps',
        verbose_name='Phụ thuộc bước',
    )
    step_order = models.PositiveIntegerField(default=0, verbose_name='Thứ tự')
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
            self.STATUS_BLOCKED: 'bg-secondary-subtle text-secondary',
            self.STATUS_HANDED_OFF: 'bg-secondary-subtle text-secondary',
        }
        return mapping.get(self.status, 'bg-secondary-subtle text-secondary')


class WorkTaskAttachment(models.Model):
    STAGE_ASSIGN = 'assign'
    STAGE_WORK = 'work'
    STAGE_CHOICES = [
        (STAGE_ASSIGN, 'Khi giao việc'),
        (STAGE_WORK, 'Kết quả đã làm'),
    ]

    task = models.ForeignKey(
        WorkTask,
        on_delete=models.CASCADE,
        related_name='attachments',
        verbose_name='Công việc',
    )
    file = models.FileField(
        upload_to='tasks/attachments/%Y/%m/',
        verbose_name='File đính kèm',
    )
    original_name = models.CharField(max_length=255, blank=True, verbose_name='Tên file gốc')
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='work_task_attachments',
        verbose_name='Người tải lên',
    )
    stage = models.CharField(
        max_length=10,
        choices=STAGE_CHOICES,
        default=STAGE_ASSIGN,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Đính kèm công việc'
        verbose_name_plural = 'Đính kèm công việc'

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        if self.original_name:
            return self.original_name
        return os.path.basename(self.file.name)

    @property
    def is_image(self):
        from tasks.attachment_utils import is_image_filename
        return is_image_filename(self.display_name)

    @property
    def extension(self):
        return os.path.splitext(self.display_name.lower())[1]


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
    ACTION_ATTACHMENT = 'attachment'
    ACTION_HANDOFF = 'handoff'
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
        (ACTION_ATTACHMENT, 'Đính kèm'),
        (ACTION_HANDOFF, 'Chuyển giao'),
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


class InternalProject(models.Model):
    STATUS_DRAFT = 'draft'
    STATUS_ACTIVE = 'active'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Nháp'),
        (STATUS_ACTIVE, 'Đang chạy'),
        (STATUS_COMPLETED, 'Hoàn thành'),
        (STATUS_CANCELLED, 'Đã hủy'),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='owned_internal_projects',
        verbose_name='Chủ dự án',
    )
    title = models.CharField(max_length=200, verbose_name='Tên dự án')
    description = models.TextField(blank=True, verbose_name='Mô tả')
    due_date = models.DateField(null=True, blank=True, verbose_name='Hạn dự án')
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True,
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='internal_projects',
        blank=True,
        verbose_name='Thành viên',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Dự án nội bộ'
        verbose_name_plural = 'Dự án nội bộ'

    def __str__(self):
        return self.title

    @property
    def completed_steps_count(self):
        return self.steps.filter(status=WorkTask.STATUS_COMPLETED).count()

    @property
    def total_steps_count(self):
        return self.steps.count()

    @property
    def progress_percent(self):
        total = self.total_steps_count
        if not total:
            return 0
        return int(self.completed_steps_count * 100 / total)


class ProjectComment(models.Model):
    project = models.ForeignKey(
        InternalProject,
        on_delete=models.CASCADE,
        related_name='comments',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='project_comments',
    )
    body = models.TextField(verbose_name='Nội dung')
    mentioned_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='mentioned_in_project_comments',
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Comment dự án'
        verbose_name_plural = 'Comment dự án'

    def __str__(self):
        return f'{self.project_id} · {self.author_id}'


class WorkTaskHandoff(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Chờ duyệt'),
        (STATUS_APPROVED, 'Đã duyệt'),
        (STATUS_REJECTED, 'Từ chối'),
    ]

    project = models.ForeignKey(
        InternalProject,
        on_delete=models.CASCADE,
        related_name='handoffs',
    )
    source_task = models.ForeignKey(
        WorkTask,
        on_delete=models.CASCADE,
        related_name='handoff_requests',
    )
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='handoffs_from',
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='handoffs_to',
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='handoffs_requested',
    )
    note = models.TextField(blank=True, verbose_name='Ghi chú chuyển giao')
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='handoffs_reviewed',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)
    created_task = models.ForeignKey(
        WorkTask,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='created_from_handoff',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Chuyển giao bước'
        verbose_name_plural = 'Chuyển giao bước'

    def __str__(self):
        return f'Handoff {self.source_task_id} → {self.to_user_id}'
