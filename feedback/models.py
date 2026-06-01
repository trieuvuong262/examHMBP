from django.conf import settings
from django.db import models


class Feedback(models.Model):
    CATEGORY_PROCESS = 'process'
    CATEGORY_ENVIRONMENT = 'environment'
    CATEGORY_TOOL = 'tool'
    CATEGORY_HR = 'hr'
    CATEGORY_OTHER = 'other'

    CATEGORY_CHOICES = [
        (CATEGORY_PROCESS, 'Quy trình'),
        (CATEGORY_ENVIRONMENT, 'Môi trường làm việc'),
        (CATEGORY_TOOL, 'Công cụ / IT'),
        (CATEGORY_HR, 'Nhân sự'),
        (CATEGORY_OTHER, 'Khác'),
    ]

    STATUS_NEW = 'new'
    STATUS_IN_REVIEW = 'in_review'
    STATUS_RESOLVED = 'resolved'
    STATUS_CLOSED = 'closed'

    STATUS_CHOICES = [
        (STATUS_NEW, 'Mới'),
        (STATUS_IN_REVIEW, 'Đang xử lý'),
        (STATUS_RESOLVED, 'Đã phản hồi'),
        (STATUS_CLOSED, 'Đã đóng'),
    ]

    OPEN_STATUSES = (STATUS_NEW, STATUS_IN_REVIEW)

    submitter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='feedbacks_submitted',
    )
    title = models.CharField('Tiêu đề', max_length=200)
    body = models.TextField('Nội dung')
    category = models.CharField(
        'Chủ đề',
        max_length=32,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_OTHER,
    )
    status = models.CharField(
        'Trạng thái',
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_NEW,
        db_index=True,
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='feedbacks_assigned',
        verbose_name='Người phụ trách',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Góp ý'
        verbose_name_plural = 'Góp ý'

    def __str__(self):
        return self.title

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES


class FeedbackReply(models.Model):
    feedback = models.ForeignKey(
        Feedback,
        on_delete=models.CASCADE,
        related_name='replies',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='feedback_replies',
    )
    body = models.TextField('Nội dung')
    is_staff_reply = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Phản hồi góp ý'
        verbose_name_plural = 'Phản hồi góp ý'

    def __str__(self):
        return f'Phản hồi #{self.pk} — {self.feedback_id}'
