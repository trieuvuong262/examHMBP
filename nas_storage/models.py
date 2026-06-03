import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class NasShareLink(models.Model):
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='nas_share_links',
    )
    rel_path = models.CharField(max_length=500)
    item_name = models.CharField(max_length=255)
    is_dir = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_by', 'rel_path', 'is_active']),
        ]

    def __str__(self):
        return f'{self.item_name} ({self.token})'

    @classmethod
    def default_expiry(cls):
        days = int(getattr(settings, 'NAS_SHARE_EXPIRE_DAYS', 30))
        return timezone.now() + timedelta(days=days)

    def is_expired(self) -> bool:
        return self.expires_at <= timezone.now()

    def is_valid(self) -> bool:
        return self.is_active and not self.is_expired()

    def deactivate_if_expired(self) -> bool:
        if self.is_active and self.is_expired():
            self.is_active = False
            self.save(update_fields=['is_active'])
            return True
        return False


class NasUserFolderAccess(models.Model):
    """Liên kết user Portal ↔ thư mục trên NAS (tùy chỉnh, thay cho map mặc định phòng ban)."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='nas_folder_accesses',
        verbose_name='Tài khoản',
    )
    label = models.CharField(max_length=120, verbose_name='Tên hiển thị')
    rel_path = models.CharField(
        max_length=500,
        verbose_name='Đường dẫn NAS',
        help_text='VD: HCNS/Annt hoặc IT/_CHUNG (tương đối gốc mount NAS)',
    )
    description = models.CharField(max_length=255, blank=True, verbose_name='Mô tả')
    sort_order = models.PositiveSmallIntegerField(default=0, verbose_name='Thứ tự')
    is_active = models.BooleanField(default=True, verbose_name='Đang dùng')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'id']
        verbose_name = 'Thư mục NAS (theo user)'
        verbose_name_plural = 'Thư mục NAS (theo user)'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'rel_path'],
                name='nas_storage_user_folder_rel_path_uniq',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.user.username}: {self.label} ({self.rel_path})'
