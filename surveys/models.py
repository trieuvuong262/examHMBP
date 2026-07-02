import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Survey(models.Model):
    title = models.CharField('Tiêu đề khảo sát', max_length=255)
    question = models.TextField(
        'Nội dung câu hỏi',
        help_text='Câu hỏi nhân viên cần trả lời.',
    )
    reference_url = models.URLField(
        'Link tham khảo',
        blank=True,
        help_text='Link tài liệu / Google Form gốc (tuỳ chọn).',
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    is_active = models.BooleanField('Đang mở', default=True)
    deadline = models.DateTimeField('Hạn nhận câu hỏi', null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='surveys_created',
        verbose_name='Người tạo',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Khảo sát'
        verbose_name_plural = 'Khảo sát'

    def __str__(self):
        return self.title

    @property
    def is_open(self):
        if not self.is_active:
            return False
        if self.deadline and timezone.now() > self.deadline:
            return False
        return True

    def get_absolute_share_path(self):
        return reverse('surveys:fill', kwargs={'token': self.token})

    def response_count(self):
        return self.responses.count()


class SurveyResponse(models.Model):
    survey = models.ForeignKey(
        Survey,
        on_delete=models.CASCADE,
        related_name='responses',
        verbose_name='Khảo sát',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='survey_responses',
        verbose_name='Nhân viên',
    )
    answer = models.TextField('Nội dung câu hỏi', blank=True)
    employee_code = models.CharField('Mã NV', max_length=50, blank=True)
    full_name = models.CharField('Họ và tên', max_length=255, blank=True)
    department_name = models.CharField('Bộ phận', max_length=255, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-submitted_at']
        verbose_name = 'Phản hồi khảo sát'
        verbose_name_plural = 'Phản hồi khảo sát'
        constraints = [
            models.UniqueConstraint(
                fields=['survey', 'user'],
                name='surveys_unique_response_per_user',
            ),
        ]

    def __str__(self):
        return f'{self.full_name or self.user_id} — {self.survey.title}'
