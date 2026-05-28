from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from hrm.choices import DEFAULT_POSITION, POSITION_CHOICES


class Profile(models.Model):
    POSITION_CHOICES = POSITION_CHOICES
    ROLE_CHOICES = [
        ('EMPLOYEE', 'Nhân viên'),
        ('HOD', 'Trưởng phòng / Quản lý trực tiếp (HOD)'),
        ('GM', 'Giám đốc / Quản lý chung (GM)'),
    ]
    
    # Kết nối 1-1 với User mặc định của Django
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    
    # Thông tin cơ bản
    full_name = models.CharField(max_length=255, verbose_name="Họ và tên", blank=True)
    position = models.CharField(
        max_length=50,
        choices=POSITION_CHOICES,
        verbose_name="Chức danh",
        blank=True,
    )

    # Quản lý phân quyền mới
    role = models.CharField(
        max_length=20, 
        choices=ROLE_CHOICES, 
        default='EMPLOYEE', 
        verbose_name="Vai trò hệ thống"
    )
    
    # Danh sách lính (Chỉ dùng cho HOD)
    subordinates = models.ManyToManyField(
        User, 
        blank=True, 
        related_name='my_hod_managers', 
        verbose_name="Nhân viên dưới quyền (Dành cho HOD)"
    )

    class Meta:
        db_table = 'assessment_profile' # Giữ nguyên để khớp với database cũ

    def __str__(self):
        return self.full_name if self.full_name else self.user.username

    def save(self, *args, **kwargs):
        """
        Ghi đè hàm save để xử lý logic: 
        1. GM ngang hàng với Admin (Staff & Superuser).
        2. Tự động thu hồi quyền nếu bị đổi từ GM xuống vai trò thấp hơn.
        """
        # Lưu đối tượng trước để đảm bảo dữ liệu ổn định
        super().save(*args, **kwargs)
        
        # Lấy instance user liên kết
        user_obj = self.user
        
        if self.role == 'GM':
            # Nếu là GM thì bơm full quyền
            if not user_obj.is_superuser or not user_obj.is_staff:
                user_obj.is_superuser = True
                user_obj.is_staff = True
                user_obj.save()
        else:
            # Nếu không phải GM và KHÔNG PHẢI tài khoản admin gốc thì hạ quyền
            # Lưu ý: 'admin' là tên tài khoản quản trị tối cao, không nên đụng vào
            if user_obj.username != 'admin' and (user_obj.is_superuser or user_obj.is_staff):
                user_obj.is_superuser = False
                user_obj.is_staff = False
                user_obj.save()


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
                'position': DEFAULT_POSITION,
                'role': 'EMPLOYEE'
            }
        )
    else:
        if not Profile.objects.filter(user=instance).exists():
            Profile.objects.create(
                user=instance,
                full_name=instance.first_name or instance.username,
                position=DEFAULT_POSITION,
                role='EMPLOYEE'
            )