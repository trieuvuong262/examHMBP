from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

# 1. Danh mục năng lực (Ví dụ: Kỹ thuật tiêm, Quy trình cấp cứu, Giao tiếp)
class Competency(models.Model):
    name = models.CharField(max_length=255, verbose_name="Tên năng lực")
    description = models.TextField(blank=True, verbose_name="Mô tả")

    def __str__(self):
        return self.name

# 2. Ngân hàng câu hỏi tổng hợp
class Question(models.Model):
    TYPE_CHOICES = (
        ('single', 'Trắc nghiệm 1 đáp án'),
        ('multiple', 'Trắc nghiệm nhiều đáp án'),
        ('essay', 'Tự luận (Văn bản)'),
        ('image', 'Trả lời bằng hình ảnh'),
    )
    
    competency = models.ForeignKey(Competency, on_delete=models.CASCADE, related_name='questions')
    content = models.TextField(verbose_name="Nội dung câu hỏi")
    q_type = models.CharField(max_length=20, choices=TYPE_CHOICES, verbose_name="Loại câu hỏi")
    image_hint = models.ImageField(upload_to='question_hints/', null=True, blank=True, verbose_name="Hình ảnh minh họa (nếu có)")
    points = models.FloatField(default=1.0, verbose_name="Điểm số")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.get_q_type_display()}] {self.content[:50]}"

# 3. Các lựa chọn cho câu hỏi trắc nghiệm
class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices')
    text = models.CharField(max_length=500, verbose_name="Nội dung đáp án")
    is_correct = models.BooleanField(default=False, verbose_name="Đáp án đúng?")

    def __str__(self):
        return self.text

# 4. Thiết lập kỳ thi (Quản lý thời gian và danh sách câu hỏi)
class Exam(models.Model):
    title = models.CharField(max_length=255, verbose_name="Tên kỳ thi")
    description = models.TextField(blank=True)
    questions = models.ManyToManyField(Question, related_name='exams', verbose_name="Danh sách câu hỏi")
    
    start_time = models.DateTimeField(verbose_name="Thời gian bắt đầu")
    end_time = models.DateTimeField(verbose_name="Thời gian kết thúc")
    duration_minutes = models.PositiveIntegerField(verbose_name="Thời gian làm bài (phút)")
    
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.title

# 5. Bài làm của nhân viên (Nơi lưu câu trả lời thực tế)
class ExamSubmission(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    start_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    
    # Tổng điểm tính toán tự động (cho trắc nghiệm)
    auto_score = models.FloatField(default=0.0)
    # Điểm do Admin chấm (cho tự luận/hình ảnh)
    manual_score = models.FloatField(default=0.0)
    
    @property
    def total_score(self):
        return self.auto_score + self.manual_score

# 6. Chi tiết từng câu trả lời của nhân viên
class UserAnswer(models.Model):
    submission = models.ForeignKey(ExamSubmission, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    
    # Lưu đáp án tùy theo loại câu hỏi
    selected_choices = models.ManyToManyField(Choice, blank=True) # Cho trắc nghiệm
    essay_answer = models.TextField(null=True, blank=True)         # Cho tự luận
    image_answer = models.ImageField(upload_to='user_uploads/', null=True, blank=True) # Cho ảnh
    
    is_graded = models.BooleanField(default=False) # Đã chấm điểm chưa (cho tự luận)
    graded_score = models.FloatField(default=0.0)