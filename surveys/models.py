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
    required_course = models.ForeignKey(
        'training.Course',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='linked_surveys',
        verbose_name='Bài học gợi ý',
        help_text='Nhân viên có thể bấm học trước (không bắt buộc) rồi quay lại khảo sát.',
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

    def viewed_count(self):
        return self.views.count()


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


class SurveyView(models.Model):
    survey = models.ForeignKey(
        Survey,
        on_delete=models.CASCADE,
        related_name='views',
        verbose_name='Khảo sát',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='survey_views',
        verbose_name='Nhân viên',
    )
    employee_code = models.CharField('Mã NV', max_length=50, blank=True)
    full_name = models.CharField('Họ và tên', max_length=255, blank=True)
    department_name = models.CharField('Bộ phận', max_length=255, blank=True)
    first_viewed_at = models.DateTimeField('Lần xem đầu', auto_now_add=True)
    last_viewed_at = models.DateTimeField('Lần xem gần nhất', auto_now=True)

    class Meta:
        ordering = ['-last_viewed_at']
        verbose_name = 'Lượt xem khảo sát'
        verbose_name_plural = 'Lượt xem khảo sát'
        constraints = [
            models.UniqueConstraint(
                fields=['survey', 'user'],
                name='surveys_unique_view_per_user',
            ),
        ]

    def __str__(self):
        return f'{self.full_name or self.user_id} đã xem {self.survey.title}'
