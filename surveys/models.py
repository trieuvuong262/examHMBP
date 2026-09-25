import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Survey(models.Model):
    title = models.CharField('Tiêu đề khảo sát', max_length=255)
    question = models.TextField(
        'Nội dung câu hỏi',
        blank=True,
        help_text='Tóm tắt các câu hỏi. Khảo sát cũ dùng ô này làm câu hỏi tự luận.',
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


class SurveyQuestion(models.Model):
    TYPE_CHOICE = 'choice'
    TYPE_TEXT = 'text'
    TYPE_CHOICES = (
        (TYPE_CHOICE, 'Chọn 1 đáp án'),
        (TYPE_TEXT, 'Nhập text'),
    )

    survey = models.ForeignKey(
        Survey,
        on_delete=models.CASCADE,
        related_name='questions',
        verbose_name='Khảo sát',
    )
    content = models.TextField('Nội dung câu hỏi')
    q_type = models.CharField(
        'Loại câu hỏi',
        max_length=20,
        choices=TYPE_CHOICES,
        default=TYPE_CHOICE,
    )
    is_required = models.BooleanField('Bắt buộc', default=True)
    sort_order = models.PositiveIntegerField('Thứ tự', default=0)

    class Meta:
        ordering = ['sort_order', 'pk']
        verbose_name = 'Câu hỏi khảo sát'
        verbose_name_plural = 'Câu hỏi khảo sát'

    def __str__(self):
        return self.content[:80]


class SurveyOption(models.Model):
    question = models.ForeignKey(
        SurveyQuestion,
        on_delete=models.CASCADE,
        related_name='options',
        verbose_name='Câu hỏi',
    )
    label = models.CharField('Đáp án', max_length=500)
    sort_order = models.PositiveIntegerField('Thứ tự', default=0)

    class Meta:
        ordering = ['sort_order', 'pk']
        verbose_name = 'Đáp án'
        verbose_name_plural = 'Đáp án'

    def __str__(self):
        return self.label


class SurveyAnswer(models.Model):
    response = models.ForeignKey(
        SurveyResponse,
        on_delete=models.CASCADE,
        related_name='answers',
        verbose_name='Phản hồi',
    )
    question = models.ForeignKey(
        SurveyQuestion,
        on_delete=models.CASCADE,
        related_name='answers',
        verbose_name='Câu hỏi',
    )
    option = models.ForeignKey(
        SurveyOption,
        on_delete=models.CASCADE,
        related_name='selections',
        null=True,
        blank=True,
        verbose_name='Đáp án đã chọn',
    )
    text_value = models.TextField('Nội dung nhập', blank=True)

    class Meta:
        ordering = ['question__sort_order', 'pk']
        verbose_name = 'Lựa chọn đáp án'
        verbose_name_plural = 'Lựa chọn đáp án'
        constraints = [
            models.UniqueConstraint(
                fields=['response', 'question'],
                name='surveys_unique_answer_per_question',
            ),
        ]

    def __str__(self):
        if self.text_value:
            return f'{self.question_id}: {self.text_value[:40]}'
        return f'{self.question_id}: {self.option_id}'


class HealthCheckCampaign(models.Model):
    """Một đợt xác minh thông tin khám sức khỏe."""

    code = models.SlugField('Mã đợt', max_length=40, unique=True)
    title = models.CharField('Tiêu đề', max_length=255)
    is_open = models.BooleanField('Đang mở', default=True, db_index=True)
    opens_at = models.DateTimeField('Được cập nhật từ', null=True, blank=True)
    closes_at = models.DateTimeField('Được cập nhật đến', null=True, blank=True)
    closed_at = models.DateTimeField('Thời điểm đóng', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def allows_update(self, now=None):
        if not self.opens_at or not self.closes_at:
            return False
        moment = now or timezone.now()
        return self.opens_at <= moment <= self.closes_at

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Đợt khám sức khỏe'
        verbose_name_plural = 'Đợt khám sức khỏe'

    def __str__(self):
        return self.title


class HealthCheckPerson(models.Model):
    """Một dòng trong danh sách khám sức khỏe."""

    campaign = models.ForeignKey(
        HealthCheckCampaign,
        on_delete=models.CASCADE,
        related_name='people',
        verbose_name='Đợt',
    )
    sort_order = models.PositiveIntegerField('STT', default=0)
    employee_code = models.CharField('Mã NV', max_length=50, blank=True, db_index=True)
    full_name = models.CharField('Họ và tên', max_length=255)
    id_number = models.CharField('Số CMND/CCCD', max_length=20, blank=True)
    phone = models.CharField('Số điện thoại', max_length=20, blank=True)
    street = models.CharField('Số nhà, đường, ấp', max_length=255, blank=True)
    ward = models.CharField('Phường/xã', max_length=255, blank=True)
    province = models.CharField('Tỉnh/thành phố', max_length=255, blank=True)

    class Meta:
        ordering = ['sort_order', 'pk']
        verbose_name = 'Người trong danh sách KSK'
        verbose_name_plural = 'Người trong danh sách KSK'
        constraints = [
            models.UniqueConstraint(
                fields=['campaign', 'employee_code'],
                condition=~models.Q(employee_code=''),
                name='surveys_ksk_unique_code',
            ),
        ]

    def __str__(self):
        return f'{self.employee_code or "—"} {self.full_name}'


class HealthCheckSubmission(models.Model):
    """Thông tin nhân viên đã xác nhận hoặc sửa cho một đợt."""

    campaign = models.ForeignKey(
        HealthCheckCampaign,
        on_delete=models.CASCADE,
        related_name='submissions',
        verbose_name='Đợt',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='health_check_submissions',
        verbose_name='Nhân viên',
    )
    person = models.ForeignKey(
        HealthCheckPerson,
        on_delete=models.CASCADE,
        related_name='submissions',
        verbose_name='Dòng danh sách',
    )
    full_name = models.CharField('Họ và tên', max_length=255)
    id_number = models.CharField('Số CMND/CCCD', max_length=20)
    phone = models.CharField('Số điện thoại', max_length=20)
    street = models.CharField('Số nhà, đường, ấp', max_length=255)
    ward = models.CharField('Phường/xã', max_length=255)
    province = models.CharField('Tỉnh/thành phố', max_length=255)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Xác nhận thông tin KSK'
        verbose_name_plural = 'Xác nhận thông tin KSK'
        constraints = [
            models.UniqueConstraint(
                fields=['campaign', 'user'],
                name='surveys_ksk_unique_submission',
            ),
        ]

    def __str__(self):
        return f'{self.full_name} — {self.campaign.code}'
