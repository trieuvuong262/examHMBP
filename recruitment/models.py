from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

from hrm.choices import POSITION_CHOICES


class JobPosting(models.Model):
    POSITION_CHOICES = POSITION_CHOICES
    title = models.CharField(max_length=255, verbose_name="Tiêu đề tuyển dụng")
    department = models.CharField(max_length=100, verbose_name="Phòng ban")
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

class Candidate(models.Model):
    STATUS_CHOICES = [
        ('new', 'Mới nộp'),
        ('reviewing', 'Đang xem xét'),
        ('interviewing', 'Đang phỏng vấn'),
        ('offered', 'Trúng tuyển (Chờ nhận việc)'),
        ('hired', 'Đã nhận việc (Onboard)'),
        ('not_onboarded', 'Không Onboard'), 
        ('rejected', 'Từ chối'),
    ]

    job_posting = models.ForeignKey(JobPosting, on_delete=models.CASCADE, related_name='candidates', verbose_name="Ứng tuyển vị trí")
    full_name = models.CharField(max_length=255, verbose_name="Họ và tên")
    email = models.EmailField(verbose_name="Email")
    phone = models.CharField(max_length=20, verbose_name="Số điện thoại")
    cv_file = models.FileField(upload_to='candidate_cvs/', verbose_name="Hồ sơ CV (PDF/Word)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new', verbose_name="Trạng thái")
    hr_note = models.TextField(blank=True, verbose_name="Ghi chú của HR")
    applied_at = models.DateTimeField(auto_now_add=True, verbose_name="Ngày nộp")
# THÔNG TIN ĐĂNG KÝ HÀNH NGHỀ (Dành cho nhân viên y tế)
    license_number = models.CharField(max_length=255, blank=True, null=True, verbose_name="Số GPHN/CCHN")
    scope_of_practice = models.CharField(max_length=255, blank=True, null=True, verbose_name="Phạm vi hành nghề")
    practice_time = models.CharField(max_length=255, blank=True, null=True, verbose_name="TG hành nghề tại CS KBCB")
    professional_position = models.CharField(max_length=255, blank=True, null=True, verbose_name="Vị trí chuyên môn")
    other_practice_time = models.CharField(max_length=255, blank=True, null=True, verbose_name="TG hành nghề tại CS khác")
    license_note = models.TextField(blank=True, null=True, verbose_name="Ghi chú CCHN")

    class Meta:
        verbose_name = "Ứng viên"
        verbose_name_plural = "Ứng viên"
        ordering = ['-applied_at']

    def __str__(self):
        return f"{self.full_name} - {self.job_posting.title}"

class Interview(models.Model):
    candidate = models.OneToOneField(Candidate, on_delete=models.CASCADE, related_name='interview', verbose_name="Ứng viên")
    interview_time = models.DateTimeField(verbose_name="Thời gian phỏng vấn")
    location = models.CharField(max_length=255, default="Phòng Họp Nhân sự", verbose_name="Địa điểm / Link Online")
    interviewers = models.ManyToManyField(User, related_name='interviews_assigned', verbose_name="Hội đồng phỏng vấn")
    result_notes = models.TextField(blank=True, verbose_name="Đánh giá sau phỏng vấn")
    passed = models.BooleanField(null=True, blank=True, verbose_name="Kết quả (Đạt/Không Đạt)")

    class Meta:
        verbose_name = "Lịch phỏng vấn"
        verbose_name_plural = "Lịch phỏng vấn"
        ordering = ['interview_time']

    def __str__(self):
        return f"Phỏng vấn: {self.candidate.full_name}"