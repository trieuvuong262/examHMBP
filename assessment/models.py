from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

# 1. Thông tin bổ sung của nhân viên
class Profile(models.Model):
    POSITION_CHOICES = [
        ('Bác Sĩ', 'Bác Sĩ'),
        ('Điều Dưỡng', 'Điều Dưỡng'),
        ('Dược Sĩ', 'Dược Sĩ'),
        ('Kỹ Thuật viên', 'Kỹ Thuật viên'),
        ('Khối Hỗ trợ', 'Khối Hỗ trợ'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    full_name = models.CharField(max_length=255, verbose_name="Họ và tên", blank=True)
    position = models.CharField(
        max_length=50, 
        choices=POSITION_CHOICES, 
        verbose_name="Chức danh", 
        blank=True
    )

    def __str__(self):
        return self.full_name if self.full_name else self.user.username

# --- SIGNAL TỰ TẠO PROFILE (Cực kỳ quan trọng) ---
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()


# 2. Danh mục năng lực
class Competency(models.Model):
    name = models.CharField(max_length=255, verbose_name="Tên năng lực")
    description = models.TextField(blank=True, verbose_name="Mô tả")

    class Meta:
        verbose_name_plural = "Danh mục năng lực"

    def __str__(self):
        return self.name

# 3. Ngân hàng câu hỏi
class Question(models.Model):
    TYPE_CHOICES = (
        ('single', 'Trắc nghiệm 1 đáp án'),
        ('multiple', 'Trắc nghiệm nhiều đáp án'),
        ('essay', 'Tự luận (Văn bản)'),
        ('image_upload', 'Trả lời bằng hình ảnh'), # Đổi từ 'image' thành 'image_upload' để khớp JS
    )
    
    competency = models.ForeignKey(Competency, on_delete=models.CASCADE, related_name='questions')
    content = models.TextField(verbose_name="Nội dung câu hỏi")
    q_type = models.CharField(max_length=20, choices=TYPE_CHOICES, verbose_name="Loại câu hỏi")
    image_hint = models.ImageField(upload_to='question_hints/', null=True, blank=True, verbose_name="Ảnh minh họa")
    points = models.FloatField(default=1.0, verbose_name="Điểm số")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.get_q_type_display()}] {self.content[:50]}"

# 4. Đáp án cho câu hỏi trắc nghiệm
class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices')
    text = models.CharField(max_length=500, verbose_name="Nội dung đáp án")
    is_correct = models.BooleanField(default=False, verbose_name="Đáp án đúng?")

    def __str__(self):
        return self.text

# 5. Thiết lập kỳ thi
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

# 6. Bài nộp của nhân viên
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
# 7. Chi tiết từng câu trả lời
class UserAnswer(models.Model):
    submission = models.ForeignKey(ExamSubmission, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    
    selected_choices = models.ManyToManyField(Choice, blank=True)
    essay_answer = models.TextField(null=True, blank=True)
    image_answer = models.ImageField(upload_to='user_uploads/', null=True, blank=True)
    
    is_graded = models.BooleanField(default=False)
    graded_score = models.FloatField(default=0.0)

# ================= SIGNALS XỬ LÝ LỖI PROFILE =================

@receiver(post_save, sender=User)
def handle_user_profile(sender, instance, created, **kwargs):
    """
    Tự động tạo Profile khi có User mới.
    Nếu User cũ chưa có Profile, tự động tạo khi có bất kỳ thay đổi nào (tránh lỗi crash Admin).
    """
    if created:
        Profile.objects.get_or_create(
            user=instance, 
            defaults={'full_name': instance.username, 'position': 'Chưa xác định'}
        )
    else:
        # Đối với User cũ: Kiểm tra xem đã có Profile chưa
        profile, created_profile = Profile.objects.get_or_create(
            user=instance,
            defaults={'full_name': instance.username, 'position': 'Chưa xác định'}
        )
        if not created_profile:
            profile.save()