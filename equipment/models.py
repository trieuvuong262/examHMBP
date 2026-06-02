import socket
import uuid

from django.conf import settings
from django.db import models

from equipment.services.qr_tag import generate_asset_tag, remove_old_qr_file, should_redraw_tag


class Device(models.Model):
    CATEGORY_CHOICES = []  # runtime — dùng services/device_categories.py

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
    device_code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='Mã thiết bị',
    )
    name = models.CharField(max_length=200, verbose_name='Tên thiết bị')
    managed_department = models.ForeignKey(
        'hrm.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_equipment',
        verbose_name='Bộ phận quản lý',
    )
    category = models.CharField(
        max_length=50, default='PC', db_index=True, verbose_name='Loại thiết bị',
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

    def get_category_display(self):
        from equipment.services.device_categories import category_label
        return category_label(self.category)

    @property
    def managed_department_label(self):
        if self.managed_department_id:
            return self.managed_department.name
        return '—'

    @property
    def is_it_equipment(self) -> bool:
        from equipment.services.device_categories import import_profile_for_code

        return import_profile_for_code(self.category) == 'it'

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
        from equipment.services.device_code import allocate_device_code, normalize_device_code

        self.total_price = self.quantity * self.unit_price

        if not self.device_code:
            self.device_code = allocate_device_code()
        else:
            self.device_code = normalize_device_code(self.device_code)

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


class DeviceCategory(models.Model):
    IMPORT_IT = 'it'
    IMPORT_MACHINE = 'machine'
    IMPORT_PROFILE_CHOICES = [
        (IMPORT_IT, 'IT (có Hostname, IP…)'),
        (IMPORT_MACHINE, 'Máy xưởng'),
    ]

    code = models.CharField(max_length=50, unique=True, verbose_name='Mã loại')
    name = models.CharField(max_length=200, verbose_name='Tên hiển thị')
    group = models.CharField(max_length=30, verbose_name='Nhóm')
    import_profile = models.CharField(
        max_length=20, choices=IMPORT_PROFILE_CHOICES, default=IMPORT_MACHINE,
        verbose_name='Mẫu import Excel',
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Thứ tự')
    is_active = models.BooleanField(default=True, verbose_name='Đang dùng')
    is_system = models.BooleanField(default=False, verbose_name='Loại hệ thống')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['group', 'sort_order', 'name']
        verbose_name = 'Loại thiết bị'
        verbose_name_plural = 'Loại thiết bị'

    def __str__(self):
        return f'{self.name} ({self.code})'

    @property
    def group_label(self):
        from equipment.categories import CATEGORY_GROUP_LABELS
        return CATEGORY_GROUP_LABELS.get(self.group, self.group)

    @property
    def device_count(self):
        return Device.objects.filter(category=self.code).count()


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


class DeviceUpdateLog(models.Model):
    ACTION_CREATE = 'create'
    ACTION_UPDATE = 'update'
    ACTION_CHOICES = [
        (ACTION_CREATE, 'Tạo mới'),
        (ACTION_UPDATE, 'Cập nhật'),
    ]

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='update_logs')
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='equipment_update_logs',
        verbose_name='Người cập nhật',
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, default=ACTION_UPDATE)
    summary = models.TextField(verbose_name='Nội dung thay đổi')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Lịch sử cập nhật thiết bị'
        verbose_name_plural = 'Lịch sử cập nhật thiết bị'

    def __str__(self):
        return f'{self.device.device_code} · {self.created_at:%Y-%m-%d %H:%M}'


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
    MACHINE_COMPANY = 'company'
    MACHINE_PERSONAL = 'personal'
    MACHINE_TYPE_CHOICES = [
        (MACHINE_COMPANY, 'Máy công ty'),
        (MACHINE_PERSONAL, 'Máy cá nhân'),
    ]

    token = models.CharField(max_length=64, unique=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='agent_install_tokens',
    )
    machine_type = models.CharField(
        max_length=20,
        choices=MACHINE_TYPE_CHOICES,
        default=MACHINE_COMPANY,
        verbose_name='Loại máy',
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
