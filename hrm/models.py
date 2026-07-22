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
    body = RichTextField(blank=True, verbose_name='Nội dung (cũ)')
    section_overrides = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Ghi đè theo mục',
        help_text='{section_id: {title?, body}}',
    )
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
    REPORT_PROFILE_PRODUCTION = 'PRODUCTION'
    REPORT_PROFILE_OFFICE = 'OFFICE'
    REPORT_PROFILE_CHOICES = [
        (REPORT_PROFILE_PRODUCTION, 'Sản xuất (bảng năng suất)'),
        (REPORT_PROFILE_OFFICE, 'Phòng ban khác (Excel / Word tự do)'),
    ]

    name = models.CharField(max_length=150, unique=True, verbose_name='Tên phòng ban')
    is_active = models.BooleanField(default=True, verbose_name='Đang sử dụng')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Thứ tự hiển thị')
    report_profile = models.CharField(
        max_length=20,
        choices=REPORT_PROFILE_CHOICES,
        default=REPORT_PROFILE_OFFICE,
        verbose_name='Mẫu báo cáo',
    )

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'Phòng ban'
        verbose_name_plural = 'Phòng ban'

    def __str__(self):
        return self.name

    @property
    def employee_count(self):
        from hrm.user_search import visible_employed_profiles

        return visible_employed_profiles(department_id=self.pk).count()

    def get_enabled_modules(self):
        from hrm.module_permissions import get_department_enabled_modules
        return get_department_enabled_modules(self)


class DepartmentPosition(models.Model):
    """Vị trí cấp phòng ban (vd. Trưởng phòng) — hiển thị trên sơ đồ, dưới phòng ban."""
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='department_positions',
        verbose_name='Phòng ban',
    )
    name = models.CharField(max_length=150, verbose_name='Tên vị trí')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Thứ tự hiển thị')
    is_active = models.BooleanField(default=True, verbose_name='Đang sử dụng')

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'Vị trí (phòng ban)'
        verbose_name_plural = 'Vị trí (phòng ban)'
        constraints = [
            models.UniqueConstraint(
                fields=['department', 'name'],
                name='hrm_department_position_dept_name_uniq',
            ),
        ]

    def __str__(self):
        return self.name


class DepartmentMenuPermission(models.Model):
    """Menu/module được phép truy cập theo phòng ban."""
    department = models.OneToOneField(
        Department,
        on_delete=models.CASCADE,
        related_name='menu_permissions',
        verbose_name='Phòng ban',
    )
    modules = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Module được phép',
        help_text='Danh sách mã module. Để trống = cho phép tất cả.',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Phân quyền menu phòng ban'
        verbose_name_plural = 'Phân quyền menu phòng ban'

    def __str__(self):
        return f'Quyền menu — {self.department.name}'

    @property
    def enabled_modules(self):
        from hrm.module_permissions import ALL_MODULE_KEYS, get_department_enabled_modules
        return get_department_enabled_modules(self.department)


class PermissionGroup(models.Model):
    """Nhóm quyền tuỳ chỉnh — gán cho từng nhân viên."""
    name = models.CharField(max_length=120, unique=True, verbose_name='Tên nhóm')
    slug = models.SlugField(max_length=120, unique=True, verbose_name='Mã nhóm')
    description = models.TextField(blank=True, verbose_name='Mô tả')
    is_system = models.BooleanField(
        default=False,
        verbose_name='Nhóm hệ thống',
        help_text='Không xóa được — dùng làm mặc định theo vai trò.',
    )
    module_permissions = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Quyền theo module',
        help_text='JSON: {module: {view, create, update, delete, export, menus?: {menu_key: {...}}}}',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Nhóm quyền'
        verbose_name_plural = 'Nhóm quyền'

    def __str__(self):
        return self.name

    def get_permissions(self):
        from hrm.group_permissions import normalize_group_permissions
        return normalize_group_permissions(self.module_permissions)

class RoleModulePermission(models.Model):
    """Phân quyền xem / cập nhật theo vai trò hệ thống (4 cấp)."""
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        unique=True,
        verbose_name='Vai trò',
    )
    module_permissions = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Quyền theo module',
        help_text='JSON: {module: {view: bool, edit: bool}}',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Phân quyền vai trò'
        verbose_name_plural = 'Phân quyền vai trò'

    def __str__(self):
        return self.get_role_display()

    def get_permissions(self):
        from hrm.role_permissions import normalize_module_permissions
        return normalize_module_permissions(self.module_permissions)


class Division(models.Model):
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='divisions',
        verbose_name='Phòng ban',
    )
    name = models.CharField(max_length=150, verbose_name='Tên bộ phận')
    is_active = models.BooleanField(default=True, verbose_name='Đang sử dụng')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Thứ tự hiển thị')

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'Bộ phận'
        verbose_name_plural = 'Bộ phận'
        constraints = [
            models.UniqueConstraint(
                fields=['department', 'name'],
                name='hrm_division_department_name_uniq',
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def employee_count(self):
        from hrm.user_search import visible_employed_profiles

        return visible_employed_profiles(division_id=self.pk).count()


class DivisionPosition(models.Model):
    """Vị trí công việc thuộc bộ phận — hiển thị trên sơ đồ (có thể chưa có NV)."""
    division = models.ForeignKey(
        Division,
        on_delete=models.CASCADE,
        related_name='positions',
        verbose_name='Bộ phận',
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='division_positions',
        verbose_name='Phòng ban',
    )
    name = models.CharField(max_length=150, verbose_name='Tên vị trí')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Thứ tự hiển thị')
    is_active = models.BooleanField(default=True, verbose_name='Đang sử dụng')

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'Vị trí (bộ phận)'
        verbose_name_plural = 'Vị trí (bộ phận)'
        constraints = [
            models.UniqueConstraint(
                fields=['division', 'name'],
                name='hrm_division_position_div_name_uniq',
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.division_id and not self.department_id:
            self.department_id = self.division.department_id
        super().save(*args, **kwargs)


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
    phone = models.CharField(
        max_length=20,
        blank=True,
        default='',
        db_index=True,
        verbose_name='Số điện thoại',
        help_text='Lưu dạng 84xxxxxxxxx — dùng gửi OTP Zalo.',
    )
    avatar = models.ImageField(
        upload_to='avatars/%Y/%m/',
        null=True,
        blank=True,
        verbose_name='Ảnh đại diện',
    )
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
    on_probation = models.BooleanField(
        default=True,
        verbose_name='Thử việc',
        db_index=True,
    )
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
    permission_group = models.ForeignKey(
        PermissionGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='profiles',
        verbose_name='Nhóm quyền',
        help_text='Quyền chi tiết theo module — ưu tiên hơn mặc định vai trò.',
    )
    
    # Danh sách nhân viên cấp dưới (Tổ trưởng / Trưởng bộ phận)
    subordinates = models.ManyToManyField(
        User,
        blank=True,
        related_name='my_hod_managers',
        verbose_name='Nhân viên cấp dưới trực tiếp',
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

    odoo_user_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Odoo res.users ID',
        help_text='Đồng bộ từ Portal khi có quyền menu Odoo.',
    )
    odoo_password_synced = models.BooleanField(
        default=False,
        verbose_name='Mật khẩu Odoo đã khớp Portal',
        help_text='True sau khi đổi/reset mật khẩu Portal và đồng bộ sang Odoo.',
    )

    class Meta:
        db_table = 'assessment_profile' # Giữ nguyên để khớp với database cũ
        constraints = [
            models.UniqueConstraint(
                fields=['phone'],
                condition=~models.Q(phone=''),
                name='uniq_profile_phone_nonempty',
            ),
        ]

    def __str__(self):
        return self.full_name if self.full_name else self.user.username

    @property
    def phone_display(self):
        from hrm.phone import format_phone_vn
        return format_phone_vn(self.phone)

    @property
    def phone_masked(self):
        from hrm.phone import mask_phone_vn
        return mask_phone_vn(self.phone)

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
        from hrm.probation import sync_probation_status

        sync_probation_status(self)
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

        # Nghỉ làm → khóa đăng nhập Portal (kể cả Giám đốc/superuser).
        # Chỉ tài khoản hệ thống `admin` được giữ nguyên.
        if user_obj.username != 'admin':
            desired_active = self.is_employed
            if user_obj.is_active != desired_active:
                user_obj.is_active = desired_active
                user_obj.save(update_fields=['is_active'])


class ProfileConcurrentPosition(models.Model):
    """Vị trí kiêm nhiệm — bổ sung ngoài vị trí chính trên Profile."""

    profile = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name='concurrent_positions',
        verbose_name='Nhân viên',
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='concurrent_position_slots',
        verbose_name='Phòng ban',
    )
    division = models.ForeignKey(
        Division,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='concurrent_position_slots',
        verbose_name='Bộ phận',
    )
    job_position = models.CharField(
        max_length=100,
        verbose_name='Vị trí',
        blank=True,
        default='',
    )
    job_title = models.CharField(max_length=100, verbose_name='Chức vụ', blank=True)
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=ROLE_EMPLOYEE,
        verbose_name='Vai trò tại vị trí kiêm nhiệm',
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Thứ tự')
    is_active = models.BooleanField(default=True, verbose_name='Đang hiệu lực')
    notes = models.CharField(max_length=255, blank=True, verbose_name='Ghi chú')
    subordinates = models.ManyToManyField(
        User,
        blank=True,
        related_name='concurrent_manager_slots',
        verbose_name='Nhân viên cấp dưới tại slot kiêm nhiệm',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'id']
        verbose_name = 'Vị trí kiêm nhiệm'
        verbose_name_plural = 'Vị trí kiêm nhiệm'
        constraints = [
            models.UniqueConstraint(
                fields=['profile', 'department', 'division', 'job_position'],
                condition=models.Q(is_active=True),
                name='hrm_concurrent_slot_active_uniq',
            ),
        ]

    def __str__(self):
        label = self.job_title or self.job_position or self.get_role_display()
        return f'{self.profile} — {label} (kiêm nhiệm)'

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.division_id and self.department_id:
            if self.division.department_id != self.department_id:
                raise ValidationError({'division': 'Bộ phận phải thuộc phòng ban đã chọn.'})
        elif self.division_id and not self.department_id:
            self.department_id = self.division.department_id

    def save(self, *args, **kwargs):
        if self.division_id and not self.department_id:
            self.department_id = self.division.department_id
        super().save(*args, **kwargs)


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