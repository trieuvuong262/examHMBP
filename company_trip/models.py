from django.conf import settings
from django.db import models
from ckeditor.fields import RichTextField

from company_trip.constants import (
    BREAKFAST_CHOICES,
    ROOM_CHOICES,
    ROOM_ORGANIZER,
    ROUTE_CHOICES,
    SHOPPING_CHOICES,
    STATUS_CHOICES,
    STATUS_REGISTERED,
    TRIP_DATES_DISPLAY,
    TRIP_DESTINATION,
    TRIP_END,
    TRIP_START,
    TRIP_TITLE,
    VEGETARIAN_CHOICES,
)


class TripSettings(models.Model):
    """Singleton pk=1 — cấu hình chuyến đi."""

    title = models.CharField(max_length=255, default=TRIP_TITLE, verbose_name='Tên sự kiện')
    destination = models.CharField(max_length=255, default=TRIP_DESTINATION, verbose_name='Điểm đến')
    start_date = models.DateField(default=TRIP_START, verbose_name='Ngày bắt đầu')
    end_date = models.DateField(default=TRIP_END, verbose_name='Ngày kết thúc')
    registration_open = models.BooleanField(default=True, verbose_name='Mở đăng ký')
    dates_display = models.CharField(
        max_length=64,
        default=TRIP_DATES_DISPLAY,
        verbose_name='Chuỗi ngày hiển thị',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Cấu hình Company Trip'
        verbose_name_plural = 'Cấu hình Company Trip'

    def __str__(self):
        return self.title

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class TripRegistration(models.Model):
    profile = models.OneToOneField(
        'hrm.Profile',
        on_delete=models.CASCADE,
        related_name='company_trip_registration',
        verbose_name='Nhân viên',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='company_trip_registrations',
        verbose_name='Tài khoản',
    )
    # Snapshot
    full_name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    gender = models.CharField(max_length=10, blank=True)
    department_name = models.CharField(max_length=150, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)

    room_type = models.CharField(
        max_length=64,
        choices=ROOM_CHOICES,
        default=ROOM_ORGANIZER,
        verbose_name='Loại phòng',
    )
    companion1 = models.ForeignKey(
        'hrm.Profile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='trip_companion1_of',
        verbose_name='Người cùng phòng 1',
    )
    companion2 = models.ForeignKey(
        'hrm.Profile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='trip_companion2_of',
        verbose_name='Người cùng phòng 2',
    )
    companion1_name = models.CharField(max_length=255, blank=True)
    companion2_name = models.CharField(max_length=255, blank=True)
    room_key = models.CharField(max_length=32, blank=True, db_index=True, verbose_name='Mã phòng')

    vegetarian = models.CharField(
        max_length=32,
        choices=VEGETARIAN_CHOICES,
        default='Không ăn chay',
        verbose_name='Ăn chay',
    )
    allergy_note = models.TextField(blank=True, verbose_name='Dị ứng')
    pickup_point = models.CharField(max_length=255, blank=True, verbose_name='Điểm đón')
    breakfast_choice = models.CharField(
        max_length=64,
        choices=BREAKFAST_CHOICES,
        default='Không ăn sáng',
        verbose_name='Ăn sáng',
    )
    route = models.CharField(
        max_length=255,
        choices=ROUTE_CHOICES,
        blank=True,
        verbose_name='Lộ trình',
    )
    detail_route = models.TextField(blank=True, verbose_name='Chi tiết lộ trình')
    shopping = models.CharField(
        max_length=32,
        choices=SHOPPING_CHOICES,
        default='Tham gia',
        verbose_name='Mua sắm chợ Đầm Nại',
    )
    note = models.TextField(blank=True, verbose_name='Ghi chú')
    organized_committee = models.BooleanField(default=False, verbose_name='BTC sắp xếp phòng')

    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_REGISTERED,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Đăng ký Company Trip'
        verbose_name_plural = 'Đăng ký Company Trip'

    def __str__(self):
        return f'{self.full_name or self.profile_id} ({self.status})'


class TripEmailTemplate(models.Model):
    subject = models.CharField(
        max_length=255,
        default='Thư mời {{ gender_prefix }} {{ fullname }} tham gia Company Trip 2026 — Vĩnh Hy',
        verbose_name='Tiêu đề',
    )
    body = RichTextField(
        blank=True,
        verbose_name='Nội dung HTML',
        help_text='Biến: {{ fullname }}, {{ gender_prefix }}, {{ dates }}, {{ destination }}, {{ register_url }}',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Mẫu email Company Trip'
        verbose_name_plural = 'Mẫu email Company Trip'

    def __str__(self):
        return self.subject[:80]

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        if not (obj.body or '').strip():
            obj.body = (
                '<p>Kính gửi {{ gender_prefix }} <strong>{{ fullname }}</strong>,</p>'
                '<p>Ban Tổ chức trân trọng mời bạn tham gia <strong>Company Trip 2026</strong> '
                'tại <strong>{{ destination }}</strong> ngày <strong>{{ dates }}</strong>.</p>'
                '<p>Vui lòng đăng ký tại: <a href="{{ register_url }}">{{ register_url }}</a></p>'
                '<p>Trân trọng,<br>Ban Tổ chức</p>'
            )
            obj.save(update_fields=['body', 'updated_at'])
        return obj


class SpinNumber(models.Model):
    number = models.PositiveIntegerField(unique=True, verbose_name='Số')
    lucky = models.BooleanField(default=False, verbose_name='Lucky')
    shown = models.BooleanField(default=False, verbose_name='Đã quay')

    class Meta:
        ordering = ['number']
        verbose_name = 'Số quay thưởng'
        verbose_name_plural = 'Số quay thưởng'

    def __str__(self):
        return f'{self.number:03d} lucky={self.lucky} shown={self.shown}'
