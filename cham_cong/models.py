"""Chấm công: địa điểm, ca, bảng công và đơn nghỉ.

Duyệt nghỉ không ghi đè ngày công. Bảng công đọc đơn đã duyệt khi hiển thị.
"""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class AttendancePolicy(models.Model):
    """Singleton pk=1. Số phép năm và hệ số tăng ca."""

    reminder_lead_minutes = models.PositiveSmallIntegerField(
        default=60,
        validators=[MinValueValidator(5), MaxValueValidator(180)],
        verbose_name='Số phút nhắc trước giờ vào ca',
    )
    annual_leave_days = models.PositiveSmallIntegerField(
        default=12,
        validators=[MaxValueValidator(40)],
        verbose_name='Số ngày phép năm',
    )
    leave_carry_max_days = models.PositiveSmallIntegerField(
        default=0,
        validators=[MaxValueValidator(40)],
        verbose_name='Số ngày phép tối đa chuyển sang năm sau',
    )
    ot_weekday_rate = models.DecimalField(
        max_digits=4, decimal_places=2, default='1.50', verbose_name='Hệ số tăng ca ngày thường',
    )
    ot_sunday_rate = models.DecimalField(
        max_digits=4, decimal_places=2, default='2.00', verbose_name='Hệ số chủ nhật',
    )
    ot_holiday_rate = models.DecimalField(
        max_digits=4, decimal_places=2, default='3.00', verbose_name='Hệ số ngày lễ',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Thiết lập chấm công'
        verbose_name_plural = 'Thiết lập chấm công'

    def __str__(self):
        return 'Thiết lập chấm công'

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class WorkSite(models.Model):
    name = models.CharField(max_length=150, verbose_name='Tên địa điểm')
    latitude = models.DecimalField(max_digits=9, decimal_places=6, verbose_name='Vĩ độ')
    longitude = models.DecimalField(max_digits=9, decimal_places=6, verbose_name='Kinh độ')
    radius_m = models.PositiveIntegerField(
        default=150,
        validators=[MinValueValidator(20), MaxValueValidator(5000)],
        verbose_name='Bán kính (mét)',
    )
    is_active = models.BooleanField(default=True, verbose_name='Đang dùng')
    note = models.CharField(max_length=255, blank=True, verbose_name='Ghi chú')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Địa điểm chấm công'
        verbose_name_plural = 'Địa điểm chấm công'

    def __str__(self):
        return self.name


class WorkSiteIp(models.Model):
    site = models.ForeignKey(
        WorkSite, on_delete=models.CASCADE, related_name='ips', verbose_name='Địa điểm',
    )
    cidr = models.CharField(
        max_length=64,
        verbose_name='IP hoặc dải IP',
        help_text='Một IP công cộng của WiFi, hoặc dải CIDR như 192.168.1.0/24.',
    )

    class Meta:
        ordering = ['cidr']
        verbose_name = 'IP WiFi'
        verbose_name_plural = 'IP WiFi'
        constraints = [
            models.UniqueConstraint(fields=['site', 'cidr'], name='cham_cong_site_ip_uniq'),
        ]

    def __str__(self):
        return self.cidr


class Shift(models.Model):
    KIND_OFFICE = 'office'
    KIND_PRODUCTION = 'production'
    KIND_OVERTIME = 'overtime'
    KIND_CHOICES = [
        (KIND_OFFICE, 'Hành chính'),
        (KIND_PRODUCTION, 'Sản xuất'),
        (KIND_OVERTIME, 'Tăng ca'),
    ]

    name = models.CharField(max_length=120, verbose_name='Tên ca')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_OFFICE, verbose_name='Loại ca')
    start_time = models.TimeField(verbose_name='Giờ vào')
    end_time = models.TimeField(verbose_name='Giờ ra')
    break_start = models.TimeField(null=True, blank=True, verbose_name='Bắt đầu nghỉ')
    break_end = models.TimeField(null=True, blank=True, verbose_name='Kết thúc nghỉ')
    crosses_midnight = models.BooleanField(default=False, verbose_name='Ca qua đêm')
    late_grace_minutes = models.PositiveSmallIntegerField(default=5, verbose_name='Dung sai đi trễ (phút)')
    early_grace_minutes = models.PositiveSmallIntegerField(default=5, verbose_name='Dung sai về sớm (phút)')
    saturday_start = models.TimeField(default='08:00', verbose_name='Giờ vào thứ 7')
    saturday_end = models.TimeField(default='12:00', verbose_name='Giờ ra thứ 7')
    is_active = models.BooleanField(default=True, verbose_name='Đang dùng')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['start_time', 'name']
        verbose_name = 'Ca làm việc'
        verbose_name_plural = 'Ca làm việc'

    def __str__(self):
        return self.name


class ShiftAssignment(models.Model):
    """Một người một ca. Ưu tiên gán theo nhân viên, rồi bộ phận, rồi phòng ban."""

    shift = models.ForeignKey(
        Shift, on_delete=models.CASCADE, related_name='assignments', verbose_name='Ca',
    )
    department = models.ForeignKey(
        'hrm.Department', null=True, blank=True, on_delete=models.CASCADE,
        related_name='shift_assignments', verbose_name='Phòng ban',
    )
    division = models.ForeignKey(
        'hrm.Division', null=True, blank=True, on_delete=models.CASCADE,
        related_name='shift_assignments', verbose_name='Bộ phận',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE,
        related_name='shift_assignments', verbose_name='Nhân viên',
    )
    is_active = models.BooleanField(default=True, verbose_name='Đang hiệu lực')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']
        verbose_name = 'Gán ca'
        verbose_name_plural = 'Gán ca'

    def __str__(self):
        return f'{self.shift} → {self.target_label}'

    @property
    def target_label(self):
        if self.user_id:
            profile = getattr(self.user, 'profile', None)
            return getattr(profile, 'full_name', None) or self.user.username
        if self.division_id:
            return self.division.name
        if self.department_id:
            return self.department.name
        return '—'


class Holiday(models.Model):
    holiday_date = models.DateField(unique=True, verbose_name='Ngày')
    name = models.CharField(max_length=150, verbose_name='Tên ngày lễ')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-holiday_date']
        verbose_name = 'Ngày lễ'
        verbose_name_plural = 'Ngày lễ'

    def __str__(self):
        return f'{self.holiday_date:%d/%m/%Y} · {self.name}'


class AttendanceDay(models.Model):
    STATUS_OPEN = 'open'
    STATUS_MISSING_OUT = 'missing_out'
    STATUS_COMPLETE = 'complete'
    STATUS_CHOICES = [
        (STATUS_OPEN, 'Chưa chấm vào'),
        (STATUS_MISSING_OUT, 'Thiếu giờ ra'),
        (STATUS_COMPLETE, 'Đủ giờ vào ra'),
    ]
    SOURCE_LIVE = 'live'
    SOURCE_SUPPLEMENT = 'supplement'
    SOURCE_ADJUSTMENT = 'adjust'
    SOURCE_CHOICES = [
        (SOURCE_LIVE, 'Chấm trực tiếp'),
        (SOURCE_SUPPLEMENT, 'Bổ sung công'),
        (SOURCE_ADJUSTMENT, 'Chỉnh sửa công'),
    ]
    METHOD_IP = 'ip'
    METHOD_GPS = 'gps'
    METHOD_MANUAL = 'manual'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='attendance_days', verbose_name='Nhân viên',
    )
    work_date = models.DateField(verbose_name='Ngày công', db_index=True)
    shift = models.ForeignKey(
        Shift, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='attendance_days', verbose_name='Ca',
    )
    site = models.ForeignKey(
        WorkSite, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='attendance_days', verbose_name='Địa điểm',
    )
    clock_in = models.DateTimeField(null=True, blank=True, verbose_name='Giờ vào')
    clock_out = models.DateTimeField(null=True, blank=True, verbose_name='Giờ ra')
    break_out = models.DateTimeField(null=True, blank=True, verbose_name='Ra nghỉ giữa ca')
    break_in = models.DateTimeField(null=True, blank=True, verbose_name='Vào lại sau nghỉ')
    in_method = models.CharField(max_length=10, blank=True, verbose_name='Cách xác minh vào')
    out_method = models.CharField(max_length=10, blank=True, verbose_name='Cách xác minh ra')
    in_ip = models.CharField(max_length=64, blank=True)
    out_ip = models.CharField(max_length=64, blank=True)
    in_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    in_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    out_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    out_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    in_distance_m = models.PositiveIntegerField(null=True, blank=True)
    out_distance_m = models.PositiveIntegerField(null=True, blank=True)
    late_minutes = models.PositiveIntegerField(default=0, verbose_name='Đi trễ (phút)')
    early_minutes = models.PositiveIntegerField(default=0, verbose_name='Về sớm (phút)')
    shortage_minutes = models.PositiveIntegerField(default=0, verbose_name='Thiếu giờ (phút)')
    worked_minutes = models.PositiveIntegerField(default=0, verbose_name='Giờ làm (phút)')
    ot_minutes = models.PositiveIntegerField(default=0, verbose_name='Tăng ca (phút)')
    ot_rate = models.DecimalField(max_digits=4, decimal_places=2, default='0')
    work_credit = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True, verbose_name='Công',
    )
    day_kind = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_LIVE)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-work_date', '-id']
        verbose_name = 'Ngày công'
        verbose_name_plural = 'Ngày công'
        constraints = [
            models.UniqueConstraint(fields=['user', 'work_date'], name='cham_cong_user_day_uniq'),
        ]

    def __str__(self):
        return f'{self.user_id} · {self.work_date}'


class AttendanceSupplement(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Chờ duyệt'),
        (STATUS_APPROVED, 'Đã duyệt'),
        (STATUS_REJECTED, 'Từ chối'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='attendance_supplements', verbose_name='Nhân viên',
    )
    work_date = models.DateField(verbose_name='Ngày công')
    clock_in_time = models.TimeField(verbose_name='Giờ vào')
    clock_out_time = models.TimeField(verbose_name='Giờ ra')
    break_out_time = models.TimeField(null=True, blank=True, verbose_name='Ra nghỉ')
    break_in_time = models.TimeField(null=True, blank=True, verbose_name='Vào lại')
    reason = models.TextField(verbose_name='Lý do')
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True,
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='attendance_supplement_decisions', verbose_name='Người duyệt',
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=255, blank=True, verbose_name='Ghi chú duyệt')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Đơn bổ sung công'
        verbose_name_plural = 'Đơn bổ sung công'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'work_date'],
                condition=models.Q(status='pending'),
                name='cham_cong_supplement_pending_uniq',
            ),
        ]

    def __str__(self):
        return f'{self.user_id} · {self.work_date} · {self.status}'


class AttendanceLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='attendance_logs',
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='attendance_logs_about',
    )
    action = models.CharField(max_length=40, db_index=True)
    message = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Nhật ký chấm công'
        verbose_name_plural = 'Nhật ký chấm công'

    def __str__(self):
        return self.message


class TimesheetPeriod(models.Model):
    """Một dòng cho mỗi tháng. Khóa thì không chấm, bổ sung hay chỉnh công trong tháng đó."""

    year = models.PositiveSmallIntegerField(verbose_name='Năm')
    month = models.PositiveSmallIntegerField(verbose_name='Tháng')
    is_locked = models.BooleanField(default=False, verbose_name='Đã khóa')
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='locked_timesheets', verbose_name='Người khóa',
    )
    locked_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Kỳ bảng công'
        verbose_name_plural = 'Kỳ bảng công'
        constraints = [
            models.UniqueConstraint(fields=['year', 'month'], name='cham_cong_period_uniq'),
            models.CheckConstraint(
                condition=models.Q(month__gte=1, month__lte=12),
                name='cham_cong_period_month_range',
            ),
        ]

    def __str__(self):
        state = 'khóa' if self.is_locked else 'mở'
        return f'{self.month:02d}/{self.year} · {state}'


class AttendanceAdjustment(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Chờ duyệt'),
        (STATUS_APPROVED, 'Đã duyệt'),
        (STATUS_REJECTED, 'Từ chối'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='attendance_adjustments', verbose_name='Nhân viên',
    )
    work_date = models.DateField(verbose_name='Ngày công')
    clock_in_time = models.TimeField(verbose_name='Giờ vào')
    clock_out_time = models.TimeField(verbose_name='Giờ ra')
    break_out_time = models.TimeField(null=True, blank=True, verbose_name='Ra nghỉ')
    break_in_time = models.TimeField(null=True, blank=True, verbose_name='Vào lại')
    reason = models.TextField(verbose_name='Lý do chỉnh sửa')
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True,
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='attendance_adjustment_decisions', verbose_name='Người duyệt',
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=255, blank=True, verbose_name='Ghi chú duyệt')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Yêu cầu chỉnh công'
        verbose_name_plural = 'Yêu cầu chỉnh công'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'work_date'],
                condition=models.Q(status='pending'),
                name='cham_cong_adjustment_pending_uniq',
            ),
        ]

    def __str__(self):
        return f'{self.user_id} · {self.work_date} · {self.status}'


class LeaveRequest(models.Model):
    KIND_ANNUAL = 'annual'
    KIND_UNPAID = 'unpaid'
    KIND_PERSONAL = 'personal'
    KIND_LATE = 'late'
    KIND_EARLY = 'early'
    KIND_CHOICES = [
        (KIND_ANNUAL, 'Phép năm'),
        (KIND_UNPAID, 'Nghỉ không lương'),
        (KIND_PERSONAL, 'Nghỉ việc riêng'),
        (KIND_LATE, 'Xin đi trễ'),
        (KIND_EARLY, 'Xin về sớm'),
    ]
    PORTION_FULL = 'full'
    PORTION_MORNING = 'morning'
    PORTION_AFTERNOON = 'afternoon'
    PORTION_CHOICES = [
        (PORTION_FULL, 'Cả ngày'),
        (PORTION_MORNING, 'Buổi sáng'),
        (PORTION_AFTERNOON, 'Buổi chiều'),
    ]
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Chờ duyệt'),
        (STATUS_APPROVED, 'Đã duyệt'),
        (STATUS_REJECTED, 'Từ chối'),
        (STATUS_CANCELLED, 'Đã hủy'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='leave_requests', verbose_name='Nhân viên',
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, verbose_name='Loại nghỉ')
    start_date = models.DateField(verbose_name='Từ ngày')
    end_date = models.DateField(verbose_name='Đến ngày')
    portion = models.CharField(
        max_length=20, choices=PORTION_CHOICES, default=PORTION_FULL, verbose_name='Buổi',
    )
    reason = models.TextField(verbose_name='Lý do')
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True,
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='leave_decisions', verbose_name='Người duyệt',
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=255, blank=True, verbose_name='Ghi chú duyệt')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Đơn nghỉ'
        verbose_name_plural = 'Đơn nghỉ'
        indexes = [
            models.Index(fields=['user', 'status', 'start_date'], name='cham_cong_leave_user_idx'),
        ]

    def __str__(self):
        return f'{self.user_id} · {self.start_date} · {self.kind} · {self.status}'


class SalaryProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='salary_profile', verbose_name='Nhân viên',
    )
    base_salary = models.DecimalField(
        max_digits=14, decimal_places=0, default=0,
        validators=[MinValueValidator(0)], verbose_name='Lương cơ bản tháng',
    )
    meal_allowance = models.DecimalField(
        max_digits=14, decimal_places=0, default=0,
        validators=[MinValueValidator(0)], verbose_name='Phụ cấp ăn',
    )
    transport_allowance = models.DecimalField(
        max_digits=14, decimal_places=0, default=0,
        validators=[MinValueValidator(0)], verbose_name='Phụ cấp đi lại',
    )
    phone_allowance = models.DecimalField(
        max_digits=14, decimal_places=0, default=0,
        validators=[MinValueValidator(0)], verbose_name='Phụ cấp điện thoại',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Mức lương'
        verbose_name_plural = 'Mức lương'

    def __str__(self):
        return f'{self.user_id} · {self.base_salary}'


class PayrollPeriod(models.Model):
    STATUS_DRAFT = 'draft'
    STATUS_CLOSED = 'closed'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Chưa chốt'),
        (STATUS_CLOSED, 'Đã chốt'),
    ]

    year = models.PositiveSmallIntegerField(verbose_name='Năm')
    month = models.PositiveSmallIntegerField(verbose_name='Tháng')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    fund_total = models.DecimalField(max_digits=16, decimal_places=0, null=True, blank=True)
    calculated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='payroll_calculations',
    )
    calculated_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='payroll_closures',
    )
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Kỳ lương'
        verbose_name_plural = 'Kỳ lương'
        constraints = [
            models.UniqueConstraint(fields=['year', 'month'], name='cham_cong_payroll_period_uniq'),
            models.CheckConstraint(
                condition=models.Q(month__gte=1, month__lte=12),
                name='cham_cong_payroll_month_range',
            ),
        ]

    def __str__(self):
        return f'{self.month:02d}/{self.year} · {self.get_status_display()}'


class PayrollSlip(models.Model):
    period = models.ForeignKey(PayrollPeriod, on_delete=models.CASCADE, related_name='slips')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payroll_slips',
    )
    standard_credit = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    work_credit = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    paid_leave_credit = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    unpaid_credit = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    payable_credit = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    base_salary = models.DecimalField(max_digits=14, decimal_places=0, default=0)
    work_pay = models.DecimalField(max_digits=14, decimal_places=0, default=0)
    meal_allowance = models.DecimalField(max_digits=14, decimal_places=0, default=0)
    transport_allowance = models.DecimalField(max_digits=14, decimal_places=0, default=0)
    phone_allowance = models.DecimalField(max_digits=14, decimal_places=0, default=0)
    ot_minutes = models.PositiveIntegerField(default=0)
    ot_pay = models.DecimalField(max_digits=14, decimal_places=0, default=0)
    bonus = models.DecimalField(max_digits=14, decimal_places=0, default=0)
    penalty = models.DecimalField(max_digits=14, decimal_places=0, default=0)
    unpaid_pay = models.DecimalField(max_digits=14, decimal_places=0, default=0)
    advance = models.DecimalField(max_digits=14, decimal_places=0, default=0)
    net_pay = models.DecimalField(max_digits=14, decimal_places=0, default=0)

    class Meta:
        verbose_name = 'Phiếu lương'
        verbose_name_plural = 'Phiếu lương'
        constraints = [
            models.UniqueConstraint(fields=['period', 'user'], name='cham_cong_payroll_slip_uniq'),
        ]

    def __str__(self):
        return f'{self.user_id} · {self.period_id}'


class PayAdjustment(models.Model):
    KIND_BONUS = 'bonus'
    KIND_PENALTY = 'penalty'
    KIND_CHOICES = [
        (KIND_BONUS, 'Thưởng'),
        (KIND_PENALTY, 'Phạt'),
    ]
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Chờ duyệt'),
        (STATUS_APPROVED, 'Đã duyệt'),
        (STATUS_REJECTED, 'Từ chối'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='pay_adjustments', verbose_name='Nhân viên',
    )
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, verbose_name='Loại')
    amount = models.DecimalField(
        max_digits=14, decimal_places=0, validators=[MinValueValidator(1)],
        verbose_name='Số tiền',
    )
    reason = models.CharField(max_length=255, verbose_name='Lý do')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='pay_adjustments_created',
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='pay_adjustment_decisions',
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Thưởng phạt'
        verbose_name_plural = 'Thưởng phạt'

    def __str__(self):
        return f'{self.user_id} · {self.month:02d}/{self.year} · {self.kind}'
