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
    points = models.FloatField(default=4.0, verbose_name="Điểm số")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.get_q_type_display()}] {self.content[:50]}"

    def correct_answer_key(self) -> str:
        if self.q_type not in ('single', 'multiple'):
            return ''
        letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        labels = [
            letters[idx] if idx < len(letters) else str(idx + 1)
            for idx, choice in enumerate(self.choices.all())
            if choice.is_correct
        ]
        return ', '.join(labels)

    def correct_answer_hint(self) -> str:
        texts = [choice.text for choice in self.choices.all() if choice.is_correct]
        return ' | '.join(texts)


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
        default=50.0,
        verbose_name='Điểm đạt (cấp chứng chỉ)',
        help_text='Thang 100. Từ 50 điểm trở lên thì cấp chứng chỉ. Dưới 50 thì học lại và làm bài thi lại.',
    )
    retry_of = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='retry_exams',
        verbose_name='Đề thi lại của',
        help_text='Để trống nếu đây là đề chính. Đề thi lại dùng khi học viên dưới 50 điểm.',
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

    @property
    def source_exam(self):
        return self.retry_of or self

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
        from assessment.scoring import round_score
        return round_score((self.auto_score or 0) + (self.manual_score or 0))

    class Meta:
        verbose_name = 'Kết quả bài thi'
        verbose_name_plural = 'Kết quả bài thi'
        ordering = ['-submitted_at', '-id']

    def __str__(self):
        who = (
            getattr(getattr(self.user, 'profile', None), 'full_name', None)
            or self.user.get_full_name()
            or self.user.username
        )
        exam_title = getattr(self.exam, 'title', self.exam_id)
        return f'{who} — {exam_title}'

# 6. Chi tiết từng câu trả lời
class UserAnswer(models.Model):
    submission = models.ForeignKey(ExamSubmission, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_choices = models.ManyToManyField(Choice, blank=True)
    essay_answer = models.TextField(null=True, blank=True)
    image_answer = models.ImageField(upload_to='user_uploads/', null=True, blank=True)
    is_graded = models.BooleanField(default=False)
    graded_score = models.FloatField(default=0.0)

    class Meta:
        verbose_name = 'Câu trả lời'
        verbose_name_plural = 'Câu trả lời'

    def __str__(self):
        return f'Câu {self.question_id} — bài {self.submission_id}'


class CertificateTemplate(models.Model):
    name = models.CharField(max_length=255, verbose_name='Tên mẫu')
    heading = models.CharField(max_length=120, default='CERTIFICATE', verbose_name='Tiêu đề lớn')
    ribbon_text = models.CharField(max_length=80, default='OF COMPLETION', verbose_name='Dòng phụ')
    presented_label = models.CharField(
        max_length=160,
        default='đã hoàn thành chương trình đào tạo nội bộ',
        verbose_name='Dòng giới thiệu',
    )
    body_text = models.TextField(
        verbose_name='Mô tả mặc định',
        help_text='Dùng khi khóa/kỳ thi chưa có mô tả riêng. Có thể dùng {name}, {exam_title}, {score}, {date}, {code}.',
        default=(
            'Chứng nhận đã hoàn thành chương trình «{exam_title}» với kết quả {score} điểm. '
            'Cấp tại JustPlay ngày {date}.'
        ),
    )
    thank_you_text = models.TextField(
        verbose_name='Lời cảm ơn',
        default=(
            'JustPlay trân trọng cảm ơn Anh/Chị đã hoàn thành chương trình đào tạo '
            'và đóng góp cho sự phát triển của công ty.'
        ),
    )
    company_name = models.CharField(
        max_length=160,
        default='CÔNG TY TNHH JUST PLAY',
        verbose_name='Tên công ty',
    )
    tax_code = models.CharField(
        max_length=32,
        default='0316184836',
        verbose_name='Mã số thuế',
    )
    hr_signer_name = models.CharField(
        max_length=120,
        blank=True,
        default='',
        verbose_name='Tên trưởng phòng HCNS',
    )
    hr_signer_title = models.CharField(
        max_length=120,
        default='Trưởng phòng HCNS',
        verbose_name='Chức danh HCNS',
    )
    hr_signature = models.ImageField(
        upload_to='certificates/signatures/',
        null=True,
        blank=True,
        verbose_name='Chữ ký PNG — Trưởng phòng HCNS',
        help_text='Ảnh PNG nền trong suốt, chữ ký đỏ/đen.',
    )
    director_signer_name = models.CharField(
        max_length=120,
        blank=True,
        default='',
        verbose_name='Tên giám đốc',
    )
    director_signer_title = models.CharField(
        max_length=120,
        default='Giám đốc',
        verbose_name='Chức danh giám đốc',
    )
    director_signature = models.ImageField(
        upload_to='certificates/signatures/',
        null=True,
        blank=True,
        verbose_name='Chữ ký PNG — Giám đốc',
        help_text='Ảnh PNG nền trong suốt, chữ ký đỏ/đen.',
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


class CertificateTemplateDescription(models.Model):
    """Mô tả khóa học / kỳ thi gắn mẫu chứng chỉ — chọn động theo khóa hoặc đề thi."""

    template = models.ForeignKey(
        CertificateTemplate,
        on_delete=models.CASCADE,
        related_name='course_descriptions',
        verbose_name='Mẫu chứng chỉ',
    )
    course = models.ForeignKey(
        'training.Course',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='certificate_descriptions',
        verbose_name='Khóa học',
    )
    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='certificate_descriptions',
        verbose_name='Kỳ thi',
    )
    description = models.TextField(
        verbose_name='Mô tả khóa học',
        help_text='Hiện trên chứng chỉ của khóa/kỳ thi này. Có thể dùng {name}, {exam_title}, {score}, {date}, {code}.',
    )

    class Meta:
        verbose_name = 'Mô tả khóa trên chứng chỉ'
        verbose_name_plural = 'Mô tả khóa trên chứng chỉ'
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(
                fields=['template', 'course'],
                condition=models.Q(course__isnull=False),
                name='uniq_cert_desc_template_course',
            ),
            models.UniqueConstraint(
                fields=['template', 'exam'],
                condition=models.Q(exam__isnull=False),
                name='uniq_cert_desc_template_exam',
            ),
        ]

    def __str__(self):
        target = getattr(self.course, 'title', None) or getattr(self.exam, 'title', None) or '—'
        return f'{self.template_id} · {target}'


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