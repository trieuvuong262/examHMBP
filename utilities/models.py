from datetime import time
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from utilities.salary_rules import ABSOLUTE_MAX_SALARY_ADVANCE, DEFAULT_MAX_SALARY_ADVANCE


def normalize_request_month(value):
    """Chuẩn hoá tháng ứng về ngày 1 — bảo đảm 1 tài khoản / 1 tháng."""
    if value is None:
        return value
    return value.replace(day=1)


class MealOrderSettings(models.Model):
    """Singleton — khung giờ đặt cơm (pk=1)."""

    order_start_time = models.TimeField(default=time(16, 0), verbose_name='Bắt đầu')
    order_end_time = models.TimeField(default=time(20, 0), verbose_name='Kết thúc')
    order_days_before = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(7)],
        verbose_name='Số ngày trước ngày ăn',
        help_text='1 = đặt vào ngày hôm trước ngày ăn',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Thiết lập đặt cơm'
        verbose_name_plural = 'Thiết lập đặt cơm'

    def __str__(self):
        return 'Thiết lập đặt cơm'

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class SalaryAdvanceSettings(models.Model):
    """Singleton — khung ngày/giờ mở ứng lương + mức ứng tối đa (pk=1)."""

    is_enabled = models.BooleanField(
        default=True,
        verbose_name='Bật ứng lương',
        help_text='Tắt = đóng đăng ký bất kể ngày trong tháng.',
    )
    open_day_start = models.PositiveSmallIntegerField(
        default=18,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        verbose_name='Ngày bắt đầu',
        help_text='Ngày trong tháng bắt đầu mở ứng (1–31).',
    )
    open_time_start = models.TimeField(
        default=time(0, 0),
        verbose_name='Giờ bắt đầu',
        help_text='Giờ phút bắt đầu mở ứng vào ngày bắt đầu.',
    )
    open_day_end = models.PositiveSmallIntegerField(
        default=19,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        verbose_name='Ngày kết thúc',
        help_text='Ngày trong tháng kết thúc mở ứng (1–31).',
    )
    open_time_end = models.TimeField(
        default=time(23, 59),
        verbose_name='Giờ kết thúc',
        help_text='Giờ phút đóng ứng vào ngày kết thúc.',
    )
    max_amount = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        default=DEFAULT_MAX_SALARY_ADVANCE,
        validators=[
            MinValueValidator(Decimal('1000')),
            MaxValueValidator(ABSOLUTE_MAX_SALARY_ADVANCE),
        ],
        verbose_name='Mức ứng tối đa (VNĐ)',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Thiết lập ứng lương'
        verbose_name_plural = 'Thiết lập ứng lương'

    def __str__(self):
        return 'Thiết lập ứng lương'

    def clean(self):
        super().clean()
        if self.open_day_start and self.open_day_end and self.open_day_end < self.open_day_start:
            raise ValidationError({'open_day_end': 'Ngày kết thúc phải ≥ ngày bắt đầu.'})
        if (
            self.open_day_start
            and self.open_day_end
            and self.open_day_start == self.open_day_end
            and self.open_time_start
            and self.open_time_end
            and self.open_time_end <= self.open_time_start
        ):
            raise ValidationError({'open_time_end': 'Giờ kết thúc phải sau giờ bắt đầu khi cùng ngày.'})

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class MealDish(models.Model):
    name = models.CharField(max_length=120, unique=True, verbose_name='Tên món')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Thứ tự')
    is_active = models.BooleanField(default=True, verbose_name='Đang dùng trong danh mục')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'Món cơm'
        verbose_name_plural = 'Món cơm'

    def __str__(self):
        return self.name


class MealDayOffering(models.Model):
    meal_date = models.DateField(verbose_name='Ngày ăn')
    dish = models.ForeignKey(
        MealDish,
        on_delete=models.CASCADE,
        related_name='day_offerings',
        verbose_name='Món',
    )
    is_offered = models.BooleanField(default=False, verbose_name='Cho phép đặt')
    # Tên món lúc HR lưu menu — không đổi khi đổi tên danh mục sau này.
    dish_name = models.CharField(max_length=120, blank=True, verbose_name='Tên món (snapshot)')

    class Meta:
        unique_together = ('meal_date', 'dish')
        ordering = ['meal_date', 'dish__sort_order', 'dish__name']
        verbose_name = 'Món trong ngày'
        verbose_name_plural = 'Món trong ngày'

    def display_name(self) -> str:
        return self.dish_name or (self.dish.name if self.dish_id else '')

    def save(self, *args, **kwargs):
        if self.is_offered and self.dish_id:
            from utilities.meal_labels import normalize_dish_display
            if not self.dish_name:
                self.dish_name = normalize_dish_display(self.dish.name)
            else:
                self.dish_name = normalize_dish_display(self.dish_name)
        super().save(*args, **kwargs)

    def __str__(self):
        flag = '✓' if self.is_offered else '—'
        return f'{self.meal_date} · {self.display_name()} {flag}'


class MealOrder(models.Model):
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='meal_orders',
        verbose_name='Nhân viên',
    )
    meal_date = models.DateField(verbose_name='Ngày ăn')
    dish = models.ForeignKey(
        MealDish,
        on_delete=models.PROTECT,
        related_name='orders',
        verbose_name='Món đã chọn',
    )
    # Tên món lúc đặt — giữ nguyên dù HR đổi tên danh mục sau này.
    dish_name = models.CharField(max_length=120, blank=True, verbose_name='Tên món (snapshot)')
    note = models.CharField(max_length=200, blank=True, verbose_name='Ghi chú')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('employee', 'meal_date')
        ordering = ['-meal_date', '-created_at']
        verbose_name = 'Đơn đặt cơm'
        verbose_name_plural = 'Đơn đặt cơm'

    def display_name(self) -> str:
        return self.dish_name or (self.dish.name if self.dish_id else '')

    def save(self, *args, **kwargs):
        if self.dish_id:
            from utilities.meal_labels import normalize_dish_display
            if not self.dish_name:
                self.dish_name = normalize_dish_display(self.dish.name)
            else:
                self.dish_name = normalize_dish_display(self.dish_name)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.employee} · {self.meal_date} · {self.display_name()}'


class MealEligibleEmployee(models.Model):
    """HR tick = nhân viên được đặt cơm. Không có dòng = không được đặt."""

    employee = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='meal_order_eligibility',
        verbose_name='Nhân viên',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Người được đặt cơm'
        verbose_name_plural = 'Người được đặt cơm'
        ordering = ['employee__username']

    def __str__(self):
        return str(self.employee)


class MealOrderDecline(models.Model):
    """NV xác nhận không đặt cơm trong ngày ăn tương ứng."""

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='meal_order_declines',
        verbose_name='Nhân viên',
    )
    meal_date = models.DateField(verbose_name='Ngày ăn')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('employee', 'meal_date')
        ordering = ['-meal_date', '-created_at']
        verbose_name = 'Từ chối đặt cơm'
        verbose_name_plural = 'Từ chối đặt cơm'

    def __str__(self):
        return f'{self.employee} · không đặt · {self.meal_date}'


class SalaryAdvanceRequest(models.Model):
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='salary_advance_requests',
        verbose_name='Nhân viên',
    )
    request_month = models.DateField(
        verbose_name='Tháng ứng',
        help_text='Mỗi tài khoản chỉ được ứng lương 1 lần trong một tháng.',
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        validators=[
            MinValueValidator(Decimal('1')),
            MaxValueValidator(ABSOLUTE_MAX_SALARY_ADVANCE),
        ],
        verbose_name='Số tiền (VNĐ)',
    )
    note = models.CharField(max_length=300, blank=True, verbose_name='Ghi chú')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['employee', 'request_month'],
                name='utilities_salaryadvance_employee_month_uniq',
            ),
        ]
        ordering = ['-request_month', '-created_at']
        verbose_name = 'Yêu cầu ứng lương'
        verbose_name_plural = 'Yêu cầu ứng lương'

    def __str__(self):
        return f'{self.employee} · {self.request_month:%m/%Y} · {self.amount:,.0f}đ'

    def clean(self):
        super().clean()
        self.request_month = normalize_request_month(self.request_month)
        if not self.employee_id or not self.request_month:
            return
        qs = SalaryAdvanceRequest.objects.filter(
            employee_id=self.employee_id,
            request_month=self.request_month,
        )
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError({
                'request_month': 'Mỗi tài khoản chỉ được ứng lương 1 lần trong một tháng.',
            })

    def save(self, *args, **kwargs):
        self.request_month = normalize_request_month(self.request_month)
        super().save(*args, **kwargs)


class SalaryAdvanceDecline(models.Model):
    """NV xác nhận không ứng lương trong tháng tương ứng."""

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='salary_advance_declines',
        verbose_name='Nhân viên',
    )
    request_month = models.DateField(verbose_name='Tháng ứng')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['employee', 'request_month'],
                name='utilities_salarydecline_employee_month_uniq',
            ),
        ]
        ordering = ['-request_month', '-created_at']
        verbose_name = 'Từ chối ứng lương'
        verbose_name_plural = 'Từ chối ứng lương'

    def __str__(self):
        return f'{self.employee} · không ứng · {self.request_month:%m/%Y}'

    def save(self, *args, **kwargs):
        self.request_month = normalize_request_month(self.request_month)
        super().save(*args, **kwargs)


class MealPushSubscription(models.Model):
    """Thiết bị/trình duyệt đăng ký nhận web push nhắc đặt cơm."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='meal_push_subscriptions',
        verbose_name='Nhân viên',
    )
    endpoint = models.TextField(unique=True, verbose_name='Push endpoint')
    p256dh = models.CharField(max_length=255, verbose_name='p256dh')
    auth = models.CharField(max_length=255, verbose_name='auth')
    user_agent = models.CharField(max_length=300, blank=True, verbose_name='User-Agent')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Đăng ký push đặt cơm'
        verbose_name_plural = 'Đăng ký push đặt cơm'

    def __str__(self):
        return f'{self.user} · push · {self.endpoint[:48]}…'

    def subscription_info(self) -> dict:
        return {
            'endpoint': self.endpoint,
            'keys': {
                'p256dh': self.p256dh,
                'auth': self.auth,
            },
        }


class MealPushReminderLog(models.Model):
    """Đã gửi push nhắc đặt cơm — tránh gửi trùng trong cùng ngày ăn."""

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='meal_push_reminder_logs',
        verbose_name='Nhân viên',
    )
    meal_date = models.DateField(verbose_name='Ngày ăn')
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('employee', 'meal_date')
        ordering = ['-sent_at']
        verbose_name = 'Log push đặt cơm'
        verbose_name_plural = 'Log push đặt cơm'

    def __str__(self):
        return f'{self.employee} · {self.meal_date} · {self.sent_at:%d/%m/%Y %H:%M}'


class PortalPushConsentLog(models.Model):
    """Nhân viên đã bấm đồng ý nhận push trên portal — không hỏi lại."""

    PERMISSION_GRANTED = 'granted'
    PERMISSION_DENIED = 'denied'
    PERMISSION_DEFAULT = 'default'
    PERMISSION_CHOICES = (
        (PERMISSION_GRANTED, 'Cho phép'),
        (PERMISSION_DENIED, 'Chặn'),
        (PERMISSION_DEFAULT, 'Chưa chọn / bỏ qua'),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='portal_push_consent',
        verbose_name='Nhân viên',
    )
    browser_permission = models.CharField(
        max_length=16,
        choices=PERMISSION_CHOICES,
        default=PERMISSION_DEFAULT,
        verbose_name='Quyền trình duyệt',
    )
    push_subscribed = models.BooleanField(
        default=False,
        verbose_name='Đã đăng ký push thiết bị',
    )
    user_agent = models.CharField(max_length=300, blank=True, verbose_name='User-Agent')
    consented_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Nhật ký đồng ý push portal'
        verbose_name_plural = 'Nhật ký đồng ý push portal'

    def __str__(self):
        return f'{self.user} · {self.get_browser_permission_display()} · {self.consented_at:%d/%m/%Y %H:%M}'


class ScheduleReminder(models.Model):
    """Nhắc lịch cá nhân — chọn thứ trong tuần, một lần hoặc lặp hàng tuần."""

    REPEAT_ONCE = 'once'
    REPEAT_WEEKLY = 'weekly'
    REPEAT_MODE_CHOICES = (
        (REPEAT_ONCE, 'Một lần'),
        (REPEAT_WEEKLY, 'Hàng tuần'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='schedule_reminders',
        verbose_name='Nhân viên',
    )
    title = models.CharField(max_length=120, verbose_name='Tiêu đề')
    body = models.TextField(blank=True, verbose_name='Nội dung')
    repeat_mode = models.CharField(
        max_length=10,
        choices=REPEAT_MODE_CHOICES,
        default=REPEAT_WEEKLY,
        verbose_name='Kiểu nhắc',
    )
    weekdays = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Các thứ trong tuần',
        help_text='ISO weekday: 1=T2 … 7=CN',
    )
    remind_time = models.TimeField(verbose_name='Giờ nhắc')
    once_date = models.DateField(
        null=True,
        blank=True,
        verbose_name='Ngày nhắc (một lần)',
    )
    is_active = models.BooleanField(default=True, verbose_name='Đang bật')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['remind_time', '-created_at']
        verbose_name = 'Nhắc lịch'
        verbose_name_plural = 'Nhắc lịch'
        indexes = [
            models.Index(fields=['is_active', 'repeat_mode'], name='util_sched_active_idx'),
        ]

    def __str__(self):
        from utilities.schedule_reminder_logic import reminder_schedule_summary

        return f'{self.user} · {self.title} · {reminder_schedule_summary(self)}'

    def weekday_list(self) -> list[int]:
        from utilities.schedule_reminder_logic import normalize_weekdays

        return normalize_weekdays(self.weekdays)

    @property
    def weekdays_label(self) -> str:
        from utilities.schedule_reminder_logic import format_weekdays

        return format_weekdays(self.weekdays)


class ScheduleReminderPushLog(models.Model):
    """Đã gửi push nhắc lịch — tránh gửi trùng trong cùng ngày."""

    reminder = models.ForeignKey(
        ScheduleReminder,
        on_delete=models.CASCADE,
        related_name='push_logs',
        verbose_name='Nhắc lịch',
    )
    fire_date = models.DateField(verbose_name='Ngày gửi')
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('reminder', 'fire_date')
        ordering = ['-sent_at']
        verbose_name = 'Log push nhắc lịch'
        verbose_name_plural = 'Log push nhắc lịch'

    def __str__(self):
        return f'{self.reminder_id} · {self.fire_date:%d/%m/%Y}'


def gomoku_empty_board():
    """Bàn caro 15×15, 0 = ô trống."""
    return [[0 for _ in range(15)] for _ in range(15)]


class GomokuStats(models.Model):
    """Thắng, thua, hòa và Elo của một nhân viên."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='gomoku_stats',
        verbose_name='Nhân viên',
    )
    wins = models.PositiveIntegerField(default=0, verbose_name='Thắng')
    losses = models.PositiveIntegerField(default=0, verbose_name='Thua')
    draws = models.PositiveIntegerField(default=0, verbose_name='Hòa')
    elo = models.PositiveIntegerField(default=1000, verbose_name='Elo')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Điểm Caro'
        verbose_name_plural = 'Điểm Caro'

    def __str__(self):
        return f'{self.user_id} · {self.elo}'


class GomokuRoom(models.Model):
    """Phòng đang chờ, đang chơi, hoặc vừa kết thúc và còn chờ chơi lại."""

    STATUS_WAITING = 'waiting'
    STATUS_PLAYING = 'playing'
    STATUS_FINISHED = 'finished'
    STATUS_CLOSED = 'closed'
    STATUS_CHOICES = [
        (STATUS_WAITING, 'Đang chờ'),
        (STATUS_PLAYING, 'Đang chơi'),
        (STATUS_FINISHED, 'Đã kết thúc'),
        (STATUS_CLOSED, 'Đã đóng'),
    ]
    OPEN_STATUSES = (STATUS_WAITING, STATUS_PLAYING, STATUS_FINISHED)

    COLOR_BLACK = 'black'
    COLOR_WHITE = 'white'
    COLOR_CHOICES = [
        (COLOR_BLACK, 'Đen'),
        (COLOR_WHITE, 'Trắng'),
    ]

    code = models.CharField(max_length=4, db_index=True, verbose_name='Mã phòng')
    host = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='gomoku_rooms_hosted',
        verbose_name='Chủ phòng',
    )
    guest = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='gomoku_rooms_joined',
        null=True,
        blank=True,
        verbose_name='Người vào',
    )
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_WAITING,
        db_index=True,
        verbose_name='Trạng thái',
    )
    is_public = models.BooleanField(default=False, verbose_name='Phòng công khai')
    board = models.JSONField(default=gomoku_empty_board, verbose_name='Bàn cờ')
    host_color = models.CharField(
        max_length=8,
        choices=COLOR_CHOICES,
        default=COLOR_BLACK,
        verbose_name='Màu chủ phòng',
    )
    turn = models.CharField(
        max_length=8,
        choices=COLOR_CHOICES,
        default=COLOR_BLACK,
        verbose_name='Lượt đi',
    )
    move_count = models.PositiveIntegerField(default=0, verbose_name='Số nước')
    last_row = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='Hàng nước cuối')
    last_col = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='Cột nước cuối')
    turn_deadline = models.DateTimeField(null=True, blank=True, verbose_name='Hết giờ lượt')
    draw_offer_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        verbose_name='Người xin hòa',
    )
    undo_offer_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        verbose_name='Người xin đi lại',
    )
    host_rematch = models.BooleanField(default=False, verbose_name='Chủ phòng muốn chơi lại')
    guest_rematch = models.BooleanField(default=False, verbose_name='Khách muốn chơi lại')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Phòng Caro'
        verbose_name_plural = 'Phòng Caro'
        constraints = [
            models.UniqueConstraint(
                fields=['code'],
                condition=models.Q(status__in=['waiting', 'playing', 'finished']),
                name='utilities_gomoku_open_code_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['host', 'status'], name='util_gomoku_host_status_idx'),
            models.Index(fields=['guest', 'status'], name='util_gomoku_guest_status_idx'),
        ]

    def __str__(self):
        return f'{self.code} · {self.get_status_display()}'


class GomokuGame(models.Model):
    """Một ván đã kết thúc — dùng cho lịch sử và Elo."""

    RESULT_BLACK = 'black'
    RESULT_WHITE = 'white'
    RESULT_DRAW = 'draw'
    RESULT_CHOICES = [
        (RESULT_BLACK, 'Đen thắng'),
        (RESULT_WHITE, 'Trắng thắng'),
        (RESULT_DRAW, 'Hòa'),
    ]
    REASON_FIVE = 'five'
    REASON_RESIGN = 'resign'
    REASON_TIMEOUT = 'timeout'
    REASON_DRAW = 'draw'
    REASON_CHOICES = [
        (REASON_FIVE, 'Năm quân'),
        (REASON_RESIGN, 'Đầu hàng'),
        (REASON_TIMEOUT, 'Hết giờ'),
        (REASON_DRAW, 'Xin hòa'),
    ]

    room = models.ForeignKey(
        GomokuRoom,
        on_delete=models.CASCADE,
        related_name='games',
        verbose_name='Phòng',
    )
    black = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='gomoku_games_as_black',
        verbose_name='Quân đen',
    )
    white = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='gomoku_games_as_white',
        verbose_name='Quân trắng',
    )
    result = models.CharField(max_length=8, choices=RESULT_CHOICES, verbose_name='Kết quả')
    reason = models.CharField(max_length=16, choices=REASON_CHOICES, verbose_name='Lý do')
    black_elo_before = models.PositiveIntegerField(verbose_name='Elo đen trước ván')
    black_elo_after = models.PositiveIntegerField(verbose_name='Elo đen sau ván')
    white_elo_before = models.PositiveIntegerField(verbose_name='Elo trắng trước ván')
    white_elo_after = models.PositiveIntegerField(verbose_name='Elo trắng sau ván')
    finished_at = models.DateTimeField(auto_now_add=True, verbose_name='Kết thúc')

    class Meta:
        verbose_name = 'Ván Caro'
        verbose_name_plural = 'Ván Caro'
        ordering = ['-finished_at', '-id']
        indexes = [
            models.Index(fields=['black', 'finished_at'], name='util_gomoku_black_played_idx'),
            models.Index(fields=['white', 'finished_at'], name='util_gomoku_white_played_idx'),
        ]

    def __str__(self):
        return f'{self.black_id} vs {self.white_id} · {self.result}'


class GomokuMessage(models.Model):
    """Tin nhắn giữa hai người trong một phòng."""

    room = models.ForeignKey(
        GomokuRoom,
        on_delete=models.CASCADE,
        related_name='messages',
        verbose_name='Phòng',
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='+',
        verbose_name='Người gửi',
    )
    body = models.CharField(max_length=300, verbose_name='Nội dung')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Gửi lúc')

    class Meta:
        verbose_name = 'Tin nhắn Caro'
        verbose_name_plural = 'Tin nhắn Caro'
        ordering = ['id']
        indexes = [
            models.Index(fields=['room', 'id'], name='util_gomoku_msg_room_idx'),
        ]

    def __str__(self):
        return f'{self.room_id} · {self.sender_id}'
