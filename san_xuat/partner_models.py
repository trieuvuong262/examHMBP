"""Đối tác gia công (GĐ1) — danh mục đối tác, tài khoản cổng pn, bảng giá GC.

Tài khoản đối tác là bảng riêng (không phải auth.User) để đối tác không thể đăng nhập
portal nội bộ và không lẫn vào HRM. Mật khẩu băm bằng hasher Django.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class GcPartner(models.Model):
    code = models.CharField(max_length=40, unique=True, verbose_name='Mã đối tác')
    name = models.CharField(max_length=200, verbose_name='Tên đối tác')
    tax_code = models.CharField(max_length=40, blank=True, default='', verbose_name='MST')
    contact_name = models.CharField(max_length=120, blank=True, default='', verbose_name='Người liên hệ')
    phone = models.CharField(max_length=30, blank=True, default='', verbose_name='Điện thoại')
    email = models.EmailField(blank=True, default='', verbose_name='Email')
    address = models.CharField(max_length=255, blank=True, default='', verbose_name='Địa chỉ')
    team_slugs = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Công đoạn nhận GC',
        help_text='Danh sách slug tổ (cat/inep/theu/may/ht…).',
    )
    work_center = models.ForeignKey(
        'san_xuat.SxWorkCenter',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='gc_partners',
        verbose_name='Tổ GC trên năng lực',
    )
    capacity_per_day = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Năng lực / ngày (SP)',
    )
    payment_terms = models.CharField(max_length=120, blank=True, default='', verbose_name='Điều khoản thanh toán')
    notes = models.TextField(blank=True, default='', verbose_name='Ghi chú')
    is_active = models.BooleanField(default=True, db_index=True, verbose_name='Đang hợp tác')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )

    class Meta:
        ordering = ['name', 'code']
        verbose_name = 'Đối tác gia công'
        verbose_name_plural = 'Đối tác gia công'

    def __str__(self):
        return f'{self.code} — {self.name}'

    @property
    def team_labels(self) -> list[str]:
        from san_xuat.services.progress_template import team_by_slug

        out = []
        for slug in self.team_slugs or []:
            meta = team_by_slug(slug)
            out.append((meta or {}).get('label') or slug)
        return out


class GcPartnerAccount(models.Model):
    ROLE_OWNER = 'owner'
    ROLE_STAFF = 'staff'
    ROLE_CHOICES = [
        (ROLE_OWNER, 'Chủ / quản lý'),
        (ROLE_STAFF, 'Nhân viên báo SL'),
    ]

    partner = models.ForeignKey(
        GcPartner, on_delete=models.CASCADE, related_name='accounts', verbose_name='Đối tác',
    )
    username = models.CharField(max_length=60, unique=True, verbose_name='Tên đăng nhập')
    password = models.CharField(max_length=128, verbose_name='Mật khẩu (băm)')
    full_name = models.CharField(max_length=120, blank=True, default='', verbose_name='Họ tên')
    phone = models.CharField(max_length=30, blank=True, default='', verbose_name='Điện thoại')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=ROLE_STAFF, verbose_name='Vai trò')
    is_active = models.BooleanField(default=True, db_index=True, verbose_name='Đang hoạt động')
    must_change_password = models.BooleanField(default=True, verbose_name='Bắt buộc đổi MK')
    failed_logins = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_login = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )

    class Meta:
        ordering = ['partner__name', 'username']
        verbose_name = 'Tài khoản đối tác GC'
        verbose_name_plural = 'Tài khoản đối tác GC'

    def __str__(self):
        return self.username

    def set_password(self, raw: str) -> None:
        self.password = make_password(raw)

    def check_password(self, raw: str) -> bool:
        return bool(raw) and check_password(raw, self.password)

    @property
    def is_locked(self) -> bool:
        return bool(self.locked_until and self.locked_until > timezone.now())


class GcOutputReport(models.Model):
    """Đối tác báo sản lượng ngày × size cho một phiếu GC; QC duyệt mới ghi tiến độ."""

    STATUS_SUBMITTED = 'submitted'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_SUBMITTED, 'Chờ QC duyệt'),
        (STATUS_APPROVED, 'Đã duyệt'),
        (STATUS_REJECTED, 'Từ chối'),
        (STATUS_CANCELLED, 'Đối tác đã hủy'),
    ]

    order = models.ForeignKey(
        'san_xuat.SxSubcontractOrder', on_delete=models.CASCADE, related_name='output_reports',
    )
    partner = models.ForeignKey(GcPartner, on_delete=models.PROTECT, related_name='output_reports')
    account = models.ForeignKey(
        GcPartnerAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name='output_reports',
    )
    work_date = models.DateField(db_index=True, verbose_name='Ngày sản xuất')
    size_qtys = models.JSONField(default=dict, verbose_name='SL báo theo size')
    total_qty = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    note = models.CharField(max_length=255, blank=True, default='')
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=STATUS_SUBMITTED, db_index=True,
    )
    approved_size_qtys = models.JSONField(default=dict, blank=True, verbose_name='SL duyệt theo size')
    approved_qty = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    progress_posted = models.JSONField(
        default=dict, blank=True, help_text='{size: SL} đã ghi tiến độ tổ — để huỷ duyệt trừ đúng.',
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=255, blank=True, default='')
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        GcPartnerAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-work_date', '-pk']
        verbose_name = 'Báo sản lượng GC'
        verbose_name_plural = 'Báo sản lượng GC'

    def __str__(self):
        return f'{self.order_id} {self.work_date} {self.total_qty}'


class GcPartnerActivity(models.Model):
    """Nhật ký thao tác trên cổng pn (đăng nhập, nhận/từ chối đơn, báo/hủy sản lượng)."""

    ACTION_LOGIN = 'login'
    ACTION_LOGIN_FAILED = 'login_failed'
    ACTION_LOGOUT = 'logout'
    ACTION_PASSWORD = 'change_password'
    ACTION_ACCEPT = 'accept_order'
    ACTION_REJECT = 'reject_order'
    ACTION_REPORT = 'submit_report'
    ACTION_CANCEL_REPORT = 'cancel_report'
    ACTION_CHOICES = [
        (ACTION_LOGIN, 'Đăng nhập'),
        (ACTION_LOGIN_FAILED, 'Đăng nhập sai'),
        (ACTION_LOGOUT, 'Đăng xuất'),
        (ACTION_PASSWORD, 'Đổi mật khẩu'),
        (ACTION_ACCEPT, 'Nhận đơn'),
        (ACTION_REJECT, 'Từ chối đơn'),
        (ACTION_REPORT, 'Báo sản lượng'),
        (ACTION_CANCEL_REPORT, 'Hủy báo sản lượng'),
    ]

    partner = models.ForeignKey(
        GcPartner, on_delete=models.CASCADE, null=True, blank=True, related_name='activities',
    )
    account = models.ForeignKey(
        GcPartnerAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name='activities',
    )
    username = models.CharField(max_length=60, blank=True, default='')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, db_index=True)
    order = models.ForeignKey(
        'san_xuat.SxSubcontractOrder', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    detail = models.CharField(max_length=255, blank=True, default='')
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        verbose_name = 'Nhật ký cổng đối tác'
        verbose_name_plural = 'Nhật ký cổng đối tác'

    def __str__(self):
        return f'{self.username} {self.action} {self.created_at:%Y-%m-%d %H:%M}'


class GcKpiSnapshot(models.Model):
    """KPI tháng đã chốt của đối tác — không đổi khi dữ liệu cũ được sửa sau đó."""

    GRADE_CHOICES = [('A', 'A'), ('B', 'B'), ('C', 'C')]

    partner = models.ForeignKey(GcPartner, on_delete=models.CASCADE, related_name='kpi_snapshots')
    month = models.DateField(verbose_name='Tháng (ngày 1)')
    metrics = models.JSONField(default=dict, verbose_name='Chỉ tiêu đã chốt')
    score = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, verbose_name='Điểm')
    grade = models.CharField(max_length=1, blank=True, default='', choices=GRADE_CHOICES, verbose_name='Hạng')
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    locked_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-month', 'partner__name']
        constraints = [
            models.UniqueConstraint(fields=['partner', 'month'], name='uniq_gc_kpi_partner_month'),
        ]
        verbose_name = 'KPI gia công đã chốt'
        verbose_name_plural = 'KPI gia công đã chốt'

    def __str__(self):
        return f'{self.partner.code} {self.month:%Y-%m} {self.grade}'


class GcPriceRule(models.Model):
    """Đơn giá GC theo đối tác × mã SP × công đoạn, có hiệu lực theo ngày.

    product_code trống = giá chung cho công đoạn của đối tác.
    """

    STATUS_DRAFT = 'draft'
    STATUS_APPROVED = 'approved'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Chờ duyệt'),
        (STATUS_APPROVED, 'Đã duyệt'),
    ]

    partner = models.ForeignKey(
        GcPartner, on_delete=models.CASCADE, related_name='price_rules', verbose_name='Đối tác',
    )
    product_code = models.CharField(
        max_length=60, blank=True, default='', db_index=True, verbose_name='Mã SP (trống = chung)',
    )
    product_name = models.CharField(max_length=255, blank=True, default='')
    team_slug = models.CharField(max_length=20, db_index=True, verbose_name='Công đoạn')
    unit_price = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Đơn giá / SP (VNĐ)',
    )
    valid_from = models.DateField(verbose_name='Hiệu lực từ')
    valid_to = models.DateField(null=True, blank=True, verbose_name='Đến ngày')
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True,
    )
    notes = models.CharField(max_length=255, blank=True, default='')
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )

    class Meta:
        ordering = ['partner__name', 'team_slug', 'product_code', '-valid_from']
        verbose_name = 'Bảng giá gia công'
        verbose_name_plural = 'Bảng giá gia công'

    def __str__(self):
        return f'{self.partner.code} {self.team_slug} {self.product_code or "*"} {self.unit_price}'

    @property
    def team_label(self) -> str:
        from san_xuat.services.progress_template import team_by_slug

        return (team_by_slug(self.team_slug) or {}).get('label') or self.team_slug

    def is_effective(self, day) -> bool:
        return (
            self.status == self.STATUS_APPROVED
            and self.valid_from <= day
            and (self.valid_to is None or self.valid_to >= day)
        )
