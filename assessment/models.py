from django.db import models
from django.contrib.auth.models import User
from django.db.models import F, Max, Prefetch

# 1. Danh mục năng lực
class Competency(models.Model):
    name = models.CharField(max_length=255, verbose_name="Tên năng lực")
    description = models.TextField(blank=True, verbose_name="Mô tả")

    class Meta:
        verbose_name_plural = "Danh mục năng lực"

    def __str__(self):
        return self.name

# 2. Câu hỏi
class Question(models.Model):
    TYPE_CHOICES = (
        ('single', 'Trắc nghiệm 1 đáp án'),
        ('multiple', 'Trắc nghiệm nhiều đáp án'),
        ('essay', 'Tự luận (Văn bản)'),
        ('image_upload', 'Trả lời bằng hình ảnh'),
    )
    
    competency = models.ForeignKey(Competency, on_delete=models.CASCADE, related_name='questions')
    content = models.TextField(verbose_name="Nội dung câu hỏi")
    q_type = models.CharField(max_length=20, choices=TYPE_CHOICES, verbose_name="Loại câu hỏi")
    image_hint = models.ImageField(upload_to='question_hints/', null=True, blank=True, verbose_name="Ảnh minh họa")
    points = models.FloatField(default=1.0, verbose_name="Điểm số")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.get_q_type_display()}] {self.content[:50]}"


class ExamQuestion(models.Model):
    """Liên kết câu hỏi trong đề — có STT do admin chỉnh."""

    exam = models.ForeignKey('Exam', on_delete=models.CASCADE, related_name='exam_questions')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='exam_links')
    sort_order = models.PositiveIntegerField(default=1, verbose_name='STT trong đề')

    class Meta:
        ordering = ['sort_order', 'id']
        unique_together = ('exam', 'question')
        verbose_name = 'Câu hỏi trong đề'
        verbose_name_plural = 'Câu hỏi trong đề'

    def __str__(self):
        return f'#{self.sort_order} — {self.question}'

# 3. Đáp án
class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices')
    text = models.CharField(max_length=500, verbose_name="Nội dung đáp án")
    is_correct = models.BooleanField(default=False, verbose_name="Đáp án đúng?")
    sort_order = models.PositiveIntegerField(default=1, verbose_name='STT')

    class Meta:
        ordering = ['sort_order', 'id']
        verbose_name = 'Đáp án'
        verbose_name_plural = 'Đáp án'

    def __str__(self):
        return self.text

# 4. Đề thi
class Exam(models.Model):
    title = models.CharField(max_length=255, verbose_name="Tên kỳ thi")
    description = models.TextField(blank=True, verbose_name="Mô tả kỳ thi")
    assigned_users = models.ManyToManyField(User, related_name='assigned_exams', blank=True, verbose_name="Nhân viên dự thi")
    questions = models.ManyToManyField(
        Question,
        through='ExamQuestion',
        related_name='exams',
        verbose_name='Câu hỏi trong đề',
    )
    start_time = models.DateTimeField(verbose_name='Thời gian bắt đầu')
    end_time = models.DateTimeField(verbose_name='Thời gian kết thúc')
    duration_minutes = models.PositiveIntegerField(verbose_name='Thời gian làm bài (phút)')
    is_active = models.BooleanField(default=True, verbose_name='Đang hoạt động')
    issue_certificate = models.BooleanField(
        default=True,
        verbose_name='Cấp chứng chỉ khi hoàn thành',
    )
    pass_score = models.FloatField(
        default=5.0,
        verbose_name='Điểm đạt (cấp chứng chỉ)',
        help_text='Thí sinh đạt từ mức này trở lên mới được cấp chứng chỉ.',
    )
    certificate_template = models.ForeignKey(
        'CertificateTemplate',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='exams',
        verbose_name='Mẫu chứng chỉ',
    )

    def __str__(self):
        return self.title

    def next_sort_order(self) -> int:
        current = self.exam_questions.aggregate(m=Max('sort_order'))['m']
        return (current or 0) + 1

    def ordered_exam_questions(self):
        choice_qs = Choice.objects.order_by('sort_order', 'id')
        return (
            self.exam_questions.select_related('question', 'question__competency')
            .prefetch_related(Prefetch('question__choices', queryset=choice_qs))
            .order_by('sort_order', 'id')
        )

    def ordered_questions(self):
        choice_qs = Choice.objects.order_by('sort_order', 'id')
        return (
            Question.objects.filter(exam_links__exam=self)
            .annotate(sort_order=F('exam_links__sort_order'))
            .order_by('sort_order', 'exam_links__id')
            .prefetch_related(Prefetch('choices', queryset=choice_qs))
        )

    def replace_questions(self, questions, *, start_order=1):
        self.exam_questions.all().delete()
        for idx, question in enumerate(questions, start=start_order):
            ExamQuestion.objects.create(
                exam=self,
                question=question,
                sort_order=idx,
            )

# 5. Bài nộp của User
class ExamSubmission(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    start_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    auto_score = models.FloatField(default=0.0, verbose_name="Điểm máy chấm")
    manual_score = models.FloatField(default=0.0, verbose_name="Điểm Admin chấm")
    
    @property
    def total_score(self):
        return self.auto_score + self.manual_score

# 6. Chi tiết từng câu trả lời
class UserAnswer(models.Model):
    submission = models.ForeignKey(ExamSubmission, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_choices = models.ManyToManyField(Choice, blank=True)
    essay_answer = models.TextField(null=True, blank=True)
    image_answer = models.ImageField(upload_to='user_uploads/', null=True, blank=True)
    is_graded = models.BooleanField(default=False)
    graded_score = models.FloatField(default=0.0)


class CertificateTemplate(models.Model):
    name = models.CharField(max_length=255, verbose_name='Tên mẫu')
    heading = models.CharField(max_length=120, default='CERTIFICATE', verbose_name='Tiêu đề lớn')
    ribbon_text = models.CharField(max_length=80, default='OF ACHIEVEMENT', verbose_name='Dòng phụ')
    presented_label = models.CharField(
        max_length=160,
        default='THIS CERTIFICATE IS PROUDLY PRESENTED TO',
        verbose_name='Dòng giới thiệu',
    )
    body_text = models.TextField(
        verbose_name='Nội dung',
        help_text='Có thể dùng {name}, {exam_title}, {score}, {date}, {code}.',
        default=(
            'Chứng nhận đã hoàn thành kỳ thi «{exam_title}» với số điểm {score}. '
            'Chứng chỉ số {code}, cấp ngày {date}.'
        ),
    )
    issuer_name = models.CharField(max_length=120, default='JustPlay.vn', verbose_name='Đơn vị cấp')
    issuer_title = models.CharField(max_length=120, default='Ban Đào tạo', verbose_name='Chức danh ký')
    seal_text = models.CharField(max_length=40, default='JUST PLAY', verbose_name='Chữ trên huy hiệu')
    is_default = models.BooleanField(default=False, verbose_name='Mẫu mặc định')
    is_active = models.BooleanField(default=True, verbose_name='Đang dùng')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Mẫu chứng chỉ'
        verbose_name_plural = 'Mẫu chứng chỉ'
        ordering = ['-is_default', 'name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            type(self).objects.exclude(pk=self.pk).filter(is_default=True).update(is_default=False)


class Certificate(models.Model):
    code = models.CharField(max_length=32, unique=True, verbose_name='Mã chứng chỉ')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='certificates')
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='certificates')
    submission = models.ForeignKey(
        ExamSubmission,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='certificates',
    )
    template = models.ForeignKey(
        CertificateTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='issued_certificates',
    )
    recipient_name = models.CharField(max_length=255, verbose_name='Họ tên trên chứng chỉ')
    exam_title = models.CharField(max_length=255, verbose_name='Tên kỳ thi')
    score = models.FloatField(default=0, verbose_name='Điểm')
    body_text = models.TextField(blank=True, verbose_name='Nội dung đã điền')
    issued_at = models.DateTimeField(auto_now_add=True, verbose_name='Ngày cấp')
    is_revoked = models.BooleanField(default=False, verbose_name='Đã thu hồi')
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='revoked_certificates',
    )

    class Meta:
        verbose_name = 'Chứng chỉ'
        verbose_name_plural = 'Chứng chỉ'
        ordering = ['-issued_at']
        unique_together = ('user', 'exam')

    def __str__(self):
        return f'{self.code} — {self.recipient_name}'