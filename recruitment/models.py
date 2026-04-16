from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

# 1. Vị trí tuyển dụng
class JobPosting(models.Model):
    POSITION_CHOICES = [
        ('Bác Sĩ', 'Bác Sĩ'),
        ('Điều Dưỡng', 'Điều Dưỡng'),
        ('Dược Sĩ', 'Dược Sĩ'),
        ('Kỹ Thuật viên', 'Kỹ Thuật viên'),
        ('Khối Hỗ trợ', 'Khối Hỗ trợ'),
    ]
    
    title = models.CharField(max_length=255, verbose_name="Tiêu đề tuyển dụng")
    department = models.CharField(max_length=100, verbose_name="Khoa/Phòng ban")
    position = models.CharField(max_length=50, choices=POSITION_CHOICES, verbose_name="Chức danh")
    quantity = models.PositiveIntegerField(default=1, verbose_name="Số lượng cần tuyển")
    
    description = models.TextField(verbose_name="Mô tả công việc")
    requirements = models.TextField(verbose_name="Yêu cầu ứng viên", blank=True)
    
    deadline = models.DateField(verbose_name="Hạn nộp hồ sơ")
    is_active = models.BooleanField(default=True, verbose_name="Đang mở tuyển")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Vị trí tuyển dụng"
        verbose_name_plural = "Vị trí tuyển dụng"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.department})"

    @property
    def is_expired(self):
        return timezone.now().date() > self.deadline

# 2. Hồ sơ ứng viên
class Candidate(models.Model):
    STATUS_CHOICES = [
        ('new', 'Mới nộp'),
        ('reviewing', 'Đang xem xét'),
        ('interviewing', 'Đang phỏng vấn'),
        ('offered', 'Trúng tuyển (Chờ nhận việc)'),
        ('hired', 'Đã nhận việc (Onboard)'),
        ('rejected', 'Từ chối'),
    ]

    job_posting = models.ForeignKey(JobPosting, on_delete=models.CASCADE, related_name='candidates', verbose_name="Ứng tuyển vị trí")
    full_name = models.CharField(max_length=255, verbose_name="Họ và tên")
    email = models.EmailField(verbose_name="Email")
    phone = models.CharField(max_length=20, verbose_name="Số điện thoại")
    
    # File CV ứng viên nộp lên
    cv_file = models.FileField(upload_to='candidate_cvs/', verbose_name="Hồ sơ CV (PDF/Word)")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new', verbose_name="Trạng thái")
    hr_note = models.TextField(blank=True, verbose_name="Ghi chú của HR")
    
    applied_at = models.DateTimeField(auto_now_add=True, verbose_name="Ngày nộp")

    class Meta:
        verbose_name = "Ứng viên"
        verbose_name_plural = "Ứng viên"
        ordering = ['-applied_at']

    def __str__(self):
        return f"{self.full_name} - {self.job_posting.title}"

# 3. Lịch phỏng vấn
class Interview(models.Model):
    candidate = models.OneToOneField(Candidate, on_delete=models.CASCADE, related_name='interview', verbose_name="Ứng viên")
    interview_time = models.DateTimeField(verbose_name="Thời gian phỏng vấn")
    location = models.CharField(max_length=255, default="Phòng Họp Nhân sự", verbose_name="Địa điểm / Link Online")
    
    # Hội đồng phỏng vấn (Liên kết với User hệ thống)
    interviewers = models.ManyToManyField(User, related_name='interviews_assigned', verbose_name="Hội đồng phỏng vấn")
    
    result_notes = models.TextField(blank=True, verbose_name="Đánh giá sau phỏng vấn")
    passed = models.BooleanField(null=True, blank=True, verbose_name="Kết quả (Đạt/Không Đạt)")

    class Meta:
        verbose_name = "Lịch phỏng vấn"
        verbose_name_plural = "Lịch phỏng vấn"
        ordering = ['interview_time']

    def __str__(self):
        return f"Phỏng vấn: {self.candidate.full_name}"