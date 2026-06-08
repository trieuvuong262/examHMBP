from django.conf import settings
from django.db import models


class UserActivityLog(models.Model):
    ACTION_VIEW = 'view'
    ACTION_CREATE = 'create'
    ACTION_UPDATE = 'update'
    ACTION_DELETE = 'delete'
    ACTION_LOGIN = 'login'
    ACTION_LOGOUT = 'logout'
    ACTION_LOGIN_FAILED = 'login_failed'
    ACTION_EXPORT = 'export'
    ACTION_IMPORT = 'import'
    ACTION_OTHER = 'other'

    ACTION_CHOICES = [
        (ACTION_VIEW, 'Xem trang'),
        (ACTION_CREATE, 'Tạo mới'),
        (ACTION_UPDATE, 'Cập nhật'),
        (ACTION_DELETE, 'Xóa'),
        (ACTION_LOGIN, 'Đăng nhập'),
        (ACTION_LOGOUT, 'Đăng xuất'),
        (ACTION_LOGIN_FAILED, 'Đăng nhập thất bại'),
        (ACTION_EXPORT, 'Xuất dữ liệu'),
        (ACTION_IMPORT, 'Nhập dữ liệu'),
        (ACTION_OTHER, 'Khác'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activity_logs',
        verbose_name='Tài khoản',
    )
    username = models.CharField(max_length=150, blank=True, db_index=True)
    full_name = models.CharField(max_length=255, blank=True)
    department_name = models.CharField(max_length=255, blank=True)
    role = models.CharField(max_length=50, blank=True)

    action = models.CharField(max_length=32, choices=ACTION_CHOICES, db_index=True)
    module_key = models.CharField(max_length=64, blank=True, db_index=True)
    module_label = models.CharField(max_length=128, blank=True)
    summary = models.CharField(max_length=500, blank=True)

    path = models.CharField(max_length=500, blank=True, db_index=True)
    url_name = models.CharField(max_length=128, blank=True)
    method = models.CharField(max_length=10, blank=True)
    query_string = models.CharField(max_length=1000, blank=True)
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True, verbose_name='IP truy cập')
    machine_name = models.CharField(max_length=128, blank=True, db_index=True, verbose_name='Tên máy')
    user_agent = models.TextField(blank=True)
    referer = models.CharField(max_length=500, blank=True)

    object_type = models.CharField(max_length=128, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    object_repr = models.CharField(max_length=255, blank=True)

    request_data = models.JSONField(default=dict, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    extra = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Nhật ký thao tác'
        verbose_name_plural = 'Nhật ký thao tác'
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['action', '-created_at']),
            models.Index(fields=['module_key', '-created_at']),
            models.Index(fields=['username', '-created_at']),
        ]

    def __str__(self):
        who = self.full_name or self.username or 'Khách'
        return f'{who} · {self.get_action_display()} · {self.created_at:%Y-%m-%d %H:%M}'

    @property
    def action_badge_class(self):
        mapping = {
            self.ACTION_VIEW: 'bg-secondary-subtle text-secondary',
            self.ACTION_CREATE: 'bg-success-subtle text-success',
            self.ACTION_UPDATE: 'bg-primary-subtle text-primary',
            self.ACTION_DELETE: 'bg-danger-subtle text-danger',
            self.ACTION_LOGIN: 'bg-info-subtle text-info',
            self.ACTION_LOGOUT: 'bg-light text-dark border',
            self.ACTION_LOGIN_FAILED: 'bg-danger text-white',
            self.ACTION_EXPORT: 'bg-warning-subtle text-warning-emphasis',
            self.ACTION_IMPORT: 'bg-warning-subtle text-warning-emphasis',
        }
        return mapping.get(self.action, 'bg-light text-dark border')

    @property
    def client_device_display(self) -> str:
        from audit.utils import is_infrastructure_ip

        parts = []
        if self.machine_name:
            parts.append(self.machine_name)
        extra = self.extra or {}
        local_ip = extra.get('client_local_ip')
        public_ip = extra.get('client_public_ip')

        if local_ip and not is_infrastructure_ip(str(local_ip)):
            parts.append(f'LAN {local_ip}')
        if public_ip and str(public_ip) != str(local_ip) and not is_infrastructure_ip(str(public_ip)):
            parts.append(str(public_ip))
        elif not local_ip and self.ip_address and not is_infrastructure_ip(str(self.ip_address)):
            parts.append(str(self.ip_address))

        return ' · '.join(parts) if parts else '—'


class UserLoginLock(models.Model):
    """Khóa tài khoản sau quá nhiều lần nhập sai mật khẩu."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='login_lock',
        verbose_name='Tài khoản',
    )
    username_snapshot = models.CharField(max_length=150, blank=True, db_index=True)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    locked_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_failed_at = models.DateTimeField(null=True, blank=True)
    last_ip = models.GenericIPAddressField(null=True, blank=True)
    unlocked_at = models.DateTimeField(null=True, blank=True)
    unlocked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='login_locks_unlocked',
        verbose_name='IT mở khóa',
    )

    class Meta:
        verbose_name = 'Khóa đăng nhập tài khoản'
        verbose_name_plural = 'Khóa đăng nhập tài khoản'

    def __str__(self):
        return f'{self.username_snapshot or self.user_id} · {self.failed_attempts} lần sai'

    @property
    def is_locked(self) -> bool:
        return bool(self.locked_at and not self.unlocked_at)


class LoginSecurityConfig(models.Model):
    """Whitelist WAN công ty / blacklist IP (singleton pk=1)."""

    wan_whitelist_ips = models.JSONField(default=list, blank=True)
    ip_blacklist = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='login_security_configs_updated',
        verbose_name='Cập nhật bởi',
    )

    class Meta:
        verbose_name = 'Cấu hình bảo mật đăng nhập'
        verbose_name_plural = 'Cấu hình bảo mật đăng nhập'

    def __str__(self):
        return 'Cấu hình IP đăng nhập'

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class IpLoginBlock(models.Model):
    """Chặn IP do bot spam đăng nhập (user không tồn tại / quét hàng loạt)."""

    ip_address = models.GenericIPAddressField(unique=True, db_index=True)
    failed_attempts = models.PositiveIntegerField(default=0)
    unknown_username_count = models.PositiveIntegerField(default=0)
    sample_usernames = models.JSONField(default=list, blank=True)
    blocked_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_failed_at = models.DateTimeField(null=True, blank=True)
    unlocked_at = models.DateTimeField(null=True, blank=True)
    unlocked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ip_blocks_cleared',
        verbose_name='IT bỏ chặn',
    )

    class Meta:
        verbose_name = 'Chặn IP đăng nhập'
        verbose_name_plural = 'Chặn IP đăng nhập'

    def __str__(self):
        return f'{self.ip_address} · {self.failed_attempts} lần'

    @property
    def is_blocked(self) -> bool:
        return bool(self.blocked_at and not self.unlocked_at)


class PortalBackupJob(models.Model):
    TRIGGER_MANUAL = 'manual'
    TRIGGER_SCHEDULED = 'scheduled'
    TRIGGER_CHOICES = [
        (TRIGGER_MANUAL, 'Thủ công'),
        (TRIGGER_SCHEDULED, 'Tự động'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Chờ'),
        (STATUS_RUNNING, 'Đang chạy'),
        (STATUS_SUCCESS, 'Thành công'),
        (STATUS_FAILED, 'Thất bại'),
    ]

    trigger = models.CharField(max_length=16, choices=TRIGGER_CHOICES, default=TRIGGER_SCHEDULED)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='portal_backup_jobs',
    )
    remote_path = models.CharField(max_length=500, blank=True)
    message = models.TextField(blank=True)
    artifacts = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Backup Portal lên NAS'
        verbose_name_plural = 'Backup Portal lên NAS'

    def __str__(self):
        return f'{self.get_trigger_display()} · {self.get_status_display()} · {self.created_at:%Y-%m-%d %H:%M}'

    @property
    def duration_display(self) -> str:
        if not self.started_at or not self.finished_at:
            return '—'
        delta = self.finished_at - self.started_at
        secs = int(delta.total_seconds())
        if secs < 60:
            return f'{secs}s'
        return f'{secs // 60} phút {secs % 60}s'
