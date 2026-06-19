from datetime import time
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from utilities.salary_rules import MAX_SALARY_ADVANCE


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

    class Meta:
        unique_together = ('meal_date', 'dish')
        ordering = ['meal_date', 'dish__sort_order', 'dish__name']
        verbose_name = 'Món trong ngày'
        verbose_name_plural = 'Món trong ngày'

    def __str__(self):
        flag = '✓' if self.is_offered else '—'
        return f'{self.meal_date} · {self.dish.name} {flag}'


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
    note = models.CharField(max_length=200, blank=True, verbose_name='Ghi chú')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('employee', 'meal_date')
        ordering = ['-meal_date', '-created_at']
        verbose_name = 'Đơn đặt cơm'
        verbose_name_plural = 'Đơn đặt cơm'

    def __str__(self):
        return f'{self.employee} · {self.meal_date} · {self.dish.name}'


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
    request_month = models.DateField(verbose_name='Tháng ứng')
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        validators=[
            MinValueValidator(Decimal('1')),
            MaxValueValidator(MAX_SALARY_ADVANCE),
        ],
        verbose_name='Số tiền (VNĐ)',
    )
    note = models.CharField(max_length=300, blank=True, verbose_name='Ghi chú')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('employee', 'request_month')
        ordering = ['-request_month', '-created_at']
        verbose_name = 'Yêu cầu ứng lương'
        verbose_name_plural = 'Yêu cầu ứng lương'

    def __str__(self):
        return f'{self.employee} · {self.request_month:%m/%Y} · {self.amount:,.0f}đ'


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
        unique_together = ('employee', 'request_month')
        ordering = ['-request_month', '-created_at']
        verbose_name = 'Từ chối ứng lương'
        verbose_name_plural = 'Từ chối ứng lương'

    def __str__(self):
        return f'{self.employee} · không ứng · {self.request_month:%m/%Y}'


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
