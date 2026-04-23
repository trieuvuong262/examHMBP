from django.db import models
from django.contrib.auth.models import User

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

# 3. Đáp án
class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices')
    text = models.CharField(max_length=500, verbose_name="Nội dung đáp án")
    is_correct = models.BooleanField(default=False, verbose_name="Đáp án đúng?")

    def __str__(self):
        return self.text

# 4. Đề thi
class Exam(models.Model):
    title = models.CharField(max_length=255, verbose_name="Tên kỳ thi")
    description = models.TextField(blank=True, verbose_name="Mô tả kỳ thi")
    assigned_users = models.ManyToManyField(User, related_name='assigned_exams', blank=True, verbose_name="Nhân viên dự thi")
    questions = models.ManyToManyField(Question, related_name='exams', verbose_name="Câu hỏi trong đề")
    start_time = models.DateTimeField(verbose_name="Thời gian bắt đầu")
    end_time = models.DateTimeField(verbose_name="Thời gian kết thúc")
    duration_minutes = models.PositiveIntegerField(verbose_name="Thời gian làm bài (phút)")
    is_active = models.BooleanField(default=True, verbose_name="Đang hoạt động")

    def __str__(self):
        return self.title

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