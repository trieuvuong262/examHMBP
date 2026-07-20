"""Token OAuth Zalo OA — singleton, refresh_token phải persist (dùng 1 lần)."""

from __future__ import annotations

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
