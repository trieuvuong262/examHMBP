"""Đổi authorization code Zalo OA → lưu access/refresh token vào DB.

Lấy code: mở link ủy quyền OA (xem docs/integrations/zalo/README.md),
copy ``code`` từ callback URL.

Usage:
    python manage.py zalo_oauth_exchange --code '....'
    python manage.py zalo_oauth_exchange --code '....' --code-verifier '....'
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from zalo.client import ZaloAPIError, ZaloClient, zalo_is_configured


class Command(BaseCommand):
    help = 'Đổi authorization code → token OA (lưu DB)'

    def add_arguments(self, parser):
        parser.add_argument('--code', required=True, help='Authorization code từ callback Zalo')
        parser.add_argument(
            '--code-verifier',
            default='',
            help='PKCE code_verifier (nếu app bật code_challenge)',
        )

    def handle(self, *args, **options):
        if not zalo_is_configured():
            raise CommandError(
                'Thiếu ZALO_ENABLED / APP_ID / SECRET / TEMPLATE_ID. Xem zalo_status.'
            )
        try:
            result = ZaloClient().exchange_authorization_code(
                options['code'],
                code_verifier=options.get('code_verifier') or '',
            )
        except ZaloAPIError as exc:
            raise CommandError(str(exc)) from exc

        expires_at = result.get('expires_at')
        exp_s = timezone.localtime(expires_at).strftime('%d/%m/%Y %H:%M') if expires_at else '?'
        self.stdout.write(self.style.SUCCESS(f'Đã lưu token OA. access hết hạn ~ {exp_s}'))
        self.stdout.write('refresh_token đã ghi DB (không cần giữ code). Chạy zalo_status để xác nhận.')
