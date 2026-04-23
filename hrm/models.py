from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

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

    class Meta:
        db_table = 'assessment_profile' # Giữ nguyên cái này để không mất dữ liệu cũ

    def __str__(self):
        return self.full_name if self.full_name else self.user.username


# HÀM DUY NHẤT ĐỂ XỬ LÝ TỰ ĐỘNG TẠO PROFILE
@receiver(post_save, sender=User)
def handle_user_profile(sender, instance, created, **kwargs):
    """
    Tự động tạo Profile khi có User mới.
    Nếu User cũ chưa có Profile, tự động tạo khi có bất kỳ thay đổi nào.
    """
    if created:
        Profile.objects.get_or_create(
            user=instance, 
            defaults={'full_name': instance.first_name or instance.username, 'position': 'Khối Hỗ trợ'}
        )
    else:
        Profile.objects.get_or_create(
            user=instance,
            defaults={'full_name': instance.first_name or instance.username, 'position': 'Khối Hỗ trợ'}
        )