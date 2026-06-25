import uuid

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
    expires_at = models.DateTimeField(null=True, blank=True)
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
        return None

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return self.expires_at <= timezone.now()

    def is_valid(self) -> bool:
        return self.is_active and not self.is_expired()

    def deactivate_if_expired(self) -> bool:
        if self.expires_at is None:
            return False
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


class NasAccessGroup(models.Model):
    """Nhóm quyền NAS — map sang principal trên DSM (vd. @SX@ldap.justplay.local)."""

    name = models.CharField(max_length=120, unique=True, verbose_name='Tên nhóm')
    nas_principal = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='Principal trên NAS',
        help_text='VD: @SX@ldap.justplay.local hoặc @IT. Để trống → tự sinh từ tên nhóm.',
    )
    description = models.CharField(max_length=255, blank=True, verbose_name='Mô tả')
    sort_order = models.PositiveSmallIntegerField(default=0, verbose_name='Thứ tự')
    is_active = models.BooleanField(default=True, verbose_name='Đang dùng')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'Nhóm quyền NAS'
        verbose_name_plural = 'Nhóm quyền NAS'

    def __str__(self) -> str:
        return self.name

    def resolved_nas_principal(self) -> str:
        raw = (self.nas_principal or '').strip()
        if raw:
            return raw if raw.startswith('@') else f'@{raw}'
        from django.conf import settings

        domain = getattr(settings, 'NAS_LDAP_DOMAIN', 'ldap.justplay.local')
        return f'@{self.name}@{domain}'


class NasShareFolder(models.Model):
    """Shared folder đã đăng ký trên NAS (vd. 07_SAN_XUAT)."""

    share_name = models.CharField(
        max_length=120,
        unique=True,
        verbose_name='Tên share NAS',
        help_text='VD: 07_SAN_XUAT',
    )
    display_name = models.CharField(max_length=200, blank=True, verbose_name='Tên hiển thị')
    volume_path = models.CharField(
        max_length=500,
        blank=True,
        verbose_name='Đường dẫn volume',
        help_text='VD: /volume1/07_SAN_XUAT',
    )
    description = models.CharField(max_length=255, blank=True, verbose_name='Mô tả')
    sort_order = models.PositiveSmallIntegerField(default=0, verbose_name='Thứ tự')
    is_active = models.BooleanField(default=True, verbose_name='Đang dùng')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'share_name']
        verbose_name = 'Thư mục share NAS'
        verbose_name_plural = 'Thư mục share NAS'

    def __str__(self) -> str:
        return self.display_name or self.share_name

    def save(self, *args, **kwargs):
        if not (self.volume_path or '').strip():
            self.volume_path = f'/volume1/{self.share_name}'
        if not (self.display_name or '').strip():
            self.display_name = self.share_name
        super().save(*args, **kwargs)


class NasFolderPermission(models.Model):
    """Quyền chi tiết nhóm ↔ share — khớp Permission Editor DSM."""

    folder = models.ForeignKey(
        NasShareFolder,
        on_delete=models.CASCADE,
        related_name='permissions',
        verbose_name='Thư mục NAS',
    )
    group = models.ForeignKey(
        NasAccessGroup,
        on_delete=models.CASCADE,
        related_name='folder_permissions',
        verbose_name='Nhóm',
    )
    permission_type = models.CharField(
        max_length=8,
        choices=(
            ('allow', 'Cho phép'),
            ('deny', 'Từ chối'),
        ),
        default='allow',
        verbose_name='Loại',
    )
    apply_to = models.CharField(
        max_length=16,
        choices=(
            ('all', 'Tất cả'),
            ('folder', 'Chỉ thư mục này'),
            ('subfolders', 'Chỉ thư mục con'),
            ('files', 'Chỉ tệp'),
        ),
        default='all',
        verbose_name='Áp dụng cho',
    )
    inherit_from_parent = models.BooleanField(default=False, verbose_name='Kế thừa từ thư mục cha')

    perm_traverse = models.BooleanField(default=True, verbose_name='Duyệt / Thực thi')
    perm_list_read = models.BooleanField(default=True, verbose_name='Liệt kê / Đọc')
    perm_read_attr = models.BooleanField(default=True, verbose_name='Đọc thuộc tính')
    perm_read_ext_attr = models.BooleanField(default=True, verbose_name='Đọc thuộc tính mở rộng')
    perm_read_acl = models.BooleanField(default=True, verbose_name='Đọc quyền')
    perm_create_files = models.BooleanField(default=True, verbose_name='Tạo tệp / Ghi')
    perm_create_folders = models.BooleanField(default=True, verbose_name='Tạo thư mục')
    perm_write_attr = models.BooleanField(default=True, verbose_name='Ghi thuộc tính')
    perm_write_ext_attr = models.BooleanField(default=True, verbose_name='Ghi thuộc tính mở rộng')
    perm_delete_children = models.BooleanField(default=True, verbose_name='Xóa con')
    perm_delete = models.BooleanField(default=True, verbose_name='Xóa')
    perm_change_acl = models.BooleanField(default=False, verbose_name='Đổi quyền')
    perm_take_ownership = models.BooleanField(default=False, verbose_name='Chiếm sở hữu')

    last_applied_at = models.DateTimeField(null=True, blank=True, verbose_name='Áp dụng NAS lần cuối')
    last_apply_status = models.CharField(max_length=500, blank=True, verbose_name='Trạng thái áp dụng')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['folder__sort_order', 'group__sort_order', 'id']
        verbose_name = 'Phân quyền thư mục NAS'
        verbose_name_plural = 'Phân quyền thư mục NAS'
        constraints = [
            models.UniqueConstraint(
                fields=['folder', 'group'],
                name='nas_storage_folder_group_perm_uniq',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.folder.share_name} · {self.group.name}'

    def permission_flags(self) -> dict[str, bool]:
        from nas_storage.permission_defs import ALL_PERM_FIELD_NAMES

        return {name: bool(getattr(self, name)) for name in ALL_PERM_FIELD_NAMES}
