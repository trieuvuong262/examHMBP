"""Làm mới access_token từ refresh_token đã lưu (hoặc ZALO_REFRESH_TOKEN).

Usage:
    python manage.py zalo_refresh_token
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from zalo.client import ZaloAPIError, ZaloClient, zalo_has_refresh_token, zalo_is_configured


class Command(BaseCommand):
    help = 'Refresh access_token Zalo OA và lưu DB'

    def handle(self, *args, **options):
        if not zalo_is_configured():
            raise CommandError('Thiếu cấu hình ZALO_*. Xem zalo_status.')
        if not zalo_has_refresh_token():
            raise CommandError('Chưa có refresh_token. Chạy zalo_oauth_exchange trước.')
        try:
            token = ZaloClient().get_access_token()
        except ZaloAPIError as exc:
            raise CommandError(str(exc)) from exc
        from zalo.models import ZaloOAuthToken

        state = ZaloOAuthToken.get_solo()
        exp = timezone.localtime(state.expires_at).strftime('%d/%m/%Y %H:%M') if state.expires_at else '?'
        self.stdout.write(self.style.SUCCESS(
            f'Access token OK (…{token[-8:]}), hết hạn ~ {exp}'
        ))
