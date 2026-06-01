import socket
import uuid

from django.conf import settings
from django.db import models

from equipment.services.qr_tag import generate_asset_tag, remove_old_qr_file, should_redraw_tag


class Device(models.Model):
    MANAGED_IT = 'IT'
    MANAGED_MAINTENANCE = 'MAINTENANCE'
    MANAGED_OTHER = 'OTHER'
    MANAGED_CHOICES = [
        (MANAGED_IT, 'IT / CNTT'),
        (MANAGED_MAINTENANCE, 'Bảo trì xưởng'),
        (MANAGED_OTHER, 'Khác'),
    ]

    CATEGORY_CHOICES = [
        ('PC', 'Máy tính bàn (PC)'),
        ('Laptop', 'Laptop'),
        ('Printer', 'Máy in'),
        ('Network', 'Server / Thiết bị mạng'),
        ('Internet', 'Internet / Đường truyền'),
        ('Production', 'Máy sản xuất'),
        ('Tool', 'Dụng cụ / thiết bị xưởng'),
        ('CCTV', 'Camera (CCTV)'),
        ('Other', 'Khác'),
    ]

    STATUS_NEW = 'new'
    STATUS_ACTIVE = 'active'
    STATUS_BROKEN = 'broken'
    STATUS_MAINTENANCE = 'maintenance'
    STATUS_SCRAPPED = 'scrapped'
    STATUS_CHOICES = [
        (STATUS_NEW, 'Mới lắp'),
        (STATUS_ACTIVE, 'Đang hoạt động'),
        (STATUS_BROKEN, 'Đang hỏng'),
        (STATUS_MAINTENANCE, 'Đang bảo trì'),
        (STATUS_SCRAPPED, 'Đã hủy / Thanh lý'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, verbose_name='Tên thiết bị')
    managed_by = models.CharField(
        max_length=20, choices=MANAGED_CHOICES, default=MANAGED_IT, verbose_name='Bộ phận quản lý',
    )
    category = models.CharField(
        max_length=50, choices=CATEGORY_CHOICES, default='PC', verbose_name='Loại thiết bị',
    )
    usage_department = models.ForeignKey(
        'hrm.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='equipment_devices',
        verbose_name='Phòng ban sử dụng',
    )
    usage_department_text = models.CharField(
        max_length=100, blank=True, verbose_name='Phòng ban (text)',
    )
    usage_room = models.CharField(max_length=100, blank=True, verbose_name='Vị trí / phòng')
    assigned_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_equipment',
        verbose_name='Người sử dụng',
    )
    assigned_user_text = models.CharField(max_length=100, blank=True, verbose_name='Người dùng (text)')
    handover_date = models.DateField(null=True, blank=True, verbose_name='Ngày bàn giao')
    model_number = models.CharField(max_length=100, blank=True, verbose_name='Model')
    serial_number = models.CharField(max_length=100, blank=True, db_index=True, verbose_name='Serial')
    configuration = models.TextField(blank=True, verbose_name='Cấu hình')
    description = models.TextField(blank=True, verbose_name='Mô tả')
    contact_email = models.EmailField(blank=True, verbose_name='Email liên hệ')
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW, verbose_name='Trạng thái',
    )
    qr_code = models.ImageField(upload_to='equipment/qr_codes/', blank=True, null=True)
    quantity = models.PositiveIntegerField(default=1, verbose_name='Số lượng')
    unit_price = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name='Đơn giá (VNĐ)')
    total_price = models.DecimalField(
        max_digits=15, decimal_places=0, default=0, editable=False, verbose_name='Thành tiền (VNĐ)',
    )
    hostname = models.CharField(max_length=100, blank=True, verbose_name='Hostname')
    ip_address = models.GenericIPAddressField(protocol='IPv4', blank=True, null=True, verbose_name='IP')
    is_online = models.BooleanField(default=False, verbose_name='Trạng thái mạng')
    last_scan_date = models.DateTimeField(null=True, blank=True, verbose_name='Lần quét cuối')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Thiết bị'
        verbose_name_plural = 'Thiết bị'

    def __str__(self):
        return self.name

    @property
    def usage_department_label(self):
        if self.usage_department_id:
            return self.usage_department.name
        return self.usage_department_text or '—'

    @property
    def is_shared_pc(self) -> bool:
        if not self.serial_number:
            return False
        return self.agent_registrations.count() > 1

    @property
    def assigned_user_label(self):
        if self.assigned_user_id:
            profile = getattr(self.assigned_user, 'profile', None)
            if profile and profile.full_name:
                return profile.full_name
            return self.assigned_user.get_full_name() or self.assigned_user.username
        return self.assigned_user_text or '—'

    @property
    def assigned_username(self):
        if self.assigned_user_id:
            return self.assigned_user.username
        return '—'

    @property
    def assigned_position_label(self):
        if self.usage_room:
            return self.usage_room
        if self.assigned_user_id:
            from hrm.choices import DEFAULT_POSITION

            profile = getattr(self.assigned_user, 'profile', None)
            if profile:
                if profile.job_title:
                    return profile.job_title
                if profile.job_position and profile.job_position != DEFAULT_POSITION:
                    return profile.job_position
        return '—'

    @property
    def assigned_email_label(self):
        if self.contact_email:
            return self.contact_email
        if self.assigned_user_id and self.assigned_user.email:
            return self.assigned_user.email
        return '—'

    @property
    def assigned_employee_code(self):
        if self.assigned_user_id:
            profile = getattr(self.assigned_user, 'profile', None)
            if profile and profile.employee_code:
                return profile.employee_code
        return '—'

    def save(self, *args, **kwargs):
        self.total_price = self.quantity * self.unit_price

        if self.hostname and not self.ip_address:
            try:
                socket.setdefaulttimeout(1)
                self.ip_address = socket.gethostbyname(self.hostname)
            except OSError:
                pass

        update_fields = kwargs.get('update_fields')
        redraw = should_redraw_tag(update_fields)

        if redraw:
            remove_old_qr_file(self)
            tag_file, _ = generate_asset_tag(self)
            self.qr_code = tag_file
            if update_fields is not None:
                fields = list(update_fields)
                if 'qr_code' not in fields:
                    fields.append('qr_code')
                kwargs['update_fields'] = fields

        super().save(*args, **kwargs)


class MaintenanceLog(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='logs')
    service_request = models.ForeignKey(
        'service_requests.ServiceRequest',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='equipment_logs',
        verbose_name='Yêu cầu hỗ trợ',
    )
    reported_by = models.CharField(max_length=100, verbose_name='Người báo')
    reporter_email = models.EmailField(blank=True, verbose_name='Email người báo')
    issue_description = models.TextField(verbose_name='Mô tả lỗi')
    cost = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name='Chi phí sửa')
    expected_return_date = models.DateField(null=True, blank=True, verbose_name='Ngày dự kiến xong')
    completed_date = models.DateTimeField(null=True, blank=True, verbose_name='Thời gian sửa xong')
    repair_note = models.TextField(blank=True, verbose_name='Ghi chú sửa chữa')
    is_resolved = models.BooleanField(default=False, verbose_name='Đã sửa xong')
    repaired_by = models.CharField(max_length=100, blank=True, verbose_name='Người sửa')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Lịch sử bảo trì'
        verbose_name_plural = 'Lịch sử bảo trì'

    def __str__(self):
        return f'{self.device.name} · {self.created_at:%Y-%m-%d}'


class EquipmentScanControl(models.Model):
    """Tín hiệu yêu cầu agent trên các PC quét lại (singleton pk=1)."""
    agent_rescan_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Điều khiển quét Agent'

    @classmethod
    def request_agent_rescan(cls):
        from django.utils import timezone

        obj, _ = cls.objects.get_or_create(pk=1)
        obj.agent_rescan_at = timezone.now()
        obj.save(update_fields=['agent_rescan_at'])
        return obj.agent_rescan_at

    @classmethod
    def get_rescan_at(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj.agent_rescan_at


class AgentInstallToken(models.Model):
    token = models.CharField(max_length=64, unique=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='agent_install_tokens',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def is_valid(self) -> bool:
        from django.utils import timezone

        if self.used_at:
            return False
        return self.expires_at >= timezone.now()

    def mark_used(self):
        from django.utils import timezone

        self.used_at = timezone.now()
        self.save(update_fields=['used_at'])


class UserAgentRegistration(models.Model):
    """PC đã cài agent — ẩn popup cài đặt khi user login lại trên máy đó."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='agent_registrations',
    )
    serial_number = models.CharField(max_length=100, db_index=True)
    device = models.ForeignKey(
        'Device',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='agent_registrations',
    )
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('user', 'serial_number')]
        ordering = ['-registered_at']
