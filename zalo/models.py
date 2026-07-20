"""Token OAuth Zalo OA — singleton, refresh_token phải persist (dùng 1 lần)."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class ZaloOAuthToken(models.Model):
    """pk=1 — access/refresh token của OA JustPlay."""

    access_token = models.TextField(blank=True, default='')
    refresh_token = models.TextField(blank=True, default='')
    expires_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Zalo OAuth token'
        verbose_name_plural = 'Zalo OAuth tokens'

    def __str__(self):
        if self.expires_at:
            return f'Zalo token (hết hạn {timezone.localtime(self.expires_at):%d/%m/%Y %H:%M})'
        return 'Zalo token (chưa có)'

    @classmethod
    def get_solo(cls) -> 'ZaloOAuthToken':
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def access_token_valid(self, *, skew_seconds: int = 120) -> bool:
        if not self.access_token or not self.expires_at:
            return False
        return self.expires_at > timezone.now() + timezone.timedelta(seconds=skew_seconds)


class PasswordResetOtp(models.Model):
    """OTP quên mật khẩu gửi qua Zalo ZBS."""

    STATUS_PENDING = 'pending'
    STATUS_VERIFIED = 'verified'
    STATUS_USED = 'used'
    STATUS_CHOICES = (
        (STATUS_PENDING, 'Chờ xác thực'),
        (STATUS_VERIFIED, 'Đã xác thực OTP'),
        (STATUS_USED, 'Đã đặt mật khẩu'),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='password_reset_otps',
    )
    code_hash = models.CharField(max_length=64)
    session_token = models.CharField(max_length=64, unique=True, db_index=True)
    phone = models.CharField(max_length=20, blank=True, default='')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['ip_address', 'created_at']),
        ]
        verbose_name = 'OTP quên mật khẩu'
        verbose_name_plural = 'OTP quên mật khẩu'

    def __str__(self):
        return f'OTP {self.user_id} ({self.status})'

    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    def max_attempts(self) -> int:
        return max(1, int(getattr(settings, 'ZALO_OTP_MAX_ATTEMPTS', 5) or 5))

    def attempts_left(self) -> int:
        return max(0, self.max_attempts() - int(self.attempts or 0))
