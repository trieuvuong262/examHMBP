from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from ckeditor.fields import RichTextField

from hrm.choices import DEFAULT_POSITION, POSITION_CHOICES, GENDER_CHOICES
from hrm.permissions import ROLE_CHOICES, ROLE_DIRECTOR, ROLE_EMPLOYEE


class UserGuide(models.Model):
    """Singleton — nội dung trang Hướng dẫn (pk=1)."""
    title = models.CharField(
        max_length=255,
        default='Hướng dẫn sử dụng JustPlay Portal',
        verbose_name='Tiêu đề',
    )
    subtitle = models.TextField(
        blank=True,
        default=(
            'Hướng dẫn từng bước — dành cho người chưa từng dùng hệ thống. '
            'Đọc theo thứ tự hoặc nhảy tới mục bạn cần.'
        ),
        verbose_name='Mô tả ngắn',
    )
    body = RichTextField(blank=True, verbose_name='Nội dung')
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='guide_updates',
        verbose_name='Cập nhật bởi',
    )

    class Meta:
        verbose_name = 'Hướng dẫn sử dụng'
        verbose_name_plural = 'Hướng dẫn sử dụng'

    def __str__(self):
        return self.title

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def has_content(self):
        from django.utils.html import strip_tags
        return bool(strip_tags(self.body or '').strip())


class Department(models.Model):
    name = models.CharField(max_length=150, unique=True, verbose_name='Tên phòng ban')
    is_active = models.BooleanField(default=True, verbose_name='Đang sử dụng')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Thứ tự hiển thị')

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'Phòng ban'
        verbose_name_plural = 'Phòng ban'

    def __str__(self):
        return self.name

    @property
    def employee_count(self):
        return self.profiles.count()


class Division(models.Model):
    name = models.CharField(max_length=150, unique=True, verbose_name='Tên bộ phận')
    is_active = models.BooleanField(default=True, verbose_name='Đang sử dụng')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Thứ tự hiển thị')

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'Bộ phận'
        verbose_name_plural = 'Bộ phận'

    def __str__(self):
        return self.name

    @property
    def employee_count(self):
        return self.division_profiles.count()


class Profile(models.Model):
    POSITION_CHOICES = POSITION_CHOICES
    ROLE_CHOICES = ROLE_CHOICES
    
    # Kết nối 1-1 với User mặc định của Django
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    
    # Thông tin nhân sự
    employee_code = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        verbose_name='Mã NS',
    )
    full_name = models.CharField(max_length=255, verbose_name='Họ và tên', blank=True)
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='profiles',
        verbose_name='Phòng ban',
    )
    division = models.ForeignKey(
        Division,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='division_profiles',
        verbose_name='Bộ phận',
    )
    job_position = models.CharField(
        max_length=100,
        verbose_name='Vị trí',
        blank=True,
        default=DEFAULT_POSITION,
    )
    job_title = models.CharField(max_length=100, verbose_name='Chức vụ', blank=True)
    join_date = models.DateField(verbose_name='Ngày vào', null=True, blank=True)
    date_of_birth = models.DateField(verbose_name='Ngày sinh', null=True, blank=True)
    gender = models.CharField(
        max_length=1,
        choices=GENDER_CHOICES,
        verbose_name='Giới tính',
        blank=True,
    )

    role = models.CharField(
        max_length=20, 
        choices=ROLE_CHOICES, 
        default=ROLE_EMPLOYEE, 
        verbose_name="Vai trò hệ thống"
    )
    
    # Danh sách nhân viên cấp dưới (Tổ trưởng / Trưởng bộ phận)
    subordinates = models.ManyToManyField(
        User,
        blank=True,
        related_name='my_hod_managers',
        verbose_name='Nhân viên dưới quyền',
    )

    must_change_password = models.BooleanField(
        default=False,
        verbose_name="Bắt buộc đổi mật khẩu lần đầu",
    )

    is_employed = models.BooleanField(
        default=True,
        verbose_name='Đang làm việc',
        db_index=True,
    )

    class Meta:
        db_table = 'assessment_profile' # Giữ nguyên để khớp với database cũ

    def __str__(self):
        return self.full_name if self.full_name else self.user.username

    @property
    def position(self):
        return self.job_position

    @position.setter
    def position(self, value):
        self.job_position = value or DEFAULT_POSITION

    def get_gender_display_short(self):
        return dict(GENDER_CHOICES).get(self.gender, '---')

    @classmethod
    def require_password_change(cls, user):
        profile, _ = cls.objects.get_or_create(user=user)
        if not profile.must_change_password:
            profile.must_change_password = True
            profile.save(update_fields=['must_change_password'])
        return profile

    def save(self, *args, **kwargs):
        """
        Ghi đè hàm save để xử lý logic: 
        1. Giám đốc ngang hàng với Admin (Staff & Superuser).
        2. Tự động thu hồi quyền nếu bị đổi từ Giám đốc xuống vai trò thấp hơn.
        """
        # Lưu đối tượng trước để đảm bảo dữ liệu ổn định
        super().save(*args, **kwargs)
        
        # Lấy instance user liên kết
        user_obj = self.user
        
        if self.role == ROLE_DIRECTOR:
            # Giám đốc — full quyền quản trị
            if not user_obj.is_superuser or not user_obj.is_staff:
                user_obj.is_superuser = True
                user_obj.is_staff = True
                user_obj.save()
        else:
            # Không phải Giám đốc và không phải tài khoản admin gốc thì hạ quyền
            # Lưu ý: 'admin' là tên tài khoản quản trị tối cao, không nên đụng vào
            if user_obj.username != 'admin' and (user_obj.is_superuser or user_obj.is_staff):
                user_obj.is_superuser = False
                user_obj.is_staff = False
                user_obj.save()

        if user_obj.username != 'admin' and not user_obj.is_superuser:
            desired_active = self.is_employed
            if user_obj.is_active != desired_active:
                user_obj.is_active = desired_active
                user_obj.save(update_fields=['is_active'])


# =========================================================
# SIGNAL: TỰ ĐỘNG TẠO PROFILE KHI TẠO USER
# =========================================================
@receiver(post_save, sender=User)
def handle_user_profile(sender, instance, created, **kwargs):
    """
    Tự động tạo Profile khi có User mới. 
    Nếu User cũ chưa có Profile (do lỗi migrate trước đó), tự động bổ sung.
    """
    if created:
        Profile.objects.get_or_create(
            user=instance, 
            defaults={
                'full_name': instance.first_name or instance.username,
                'job_position': DEFAULT_POSITION,
                'role': ROLE_EMPLOYEE,
            }
        )
    else:
        if not Profile.objects.filter(user=instance).exists():
            Profile.objects.create(
                user=instance,
                full_name=instance.first_name or instance.username,
                job_position=DEFAULT_POSITION,
                role=ROLE_EMPLOYEE,
            )