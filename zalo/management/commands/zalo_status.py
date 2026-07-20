"""Kiểm tra cấu hình Zalo OA / ZBS OTP.

Usage:
    python manage.py zalo_status
"""

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from zalo.client import zalo_has_refresh_token, zalo_is_configured, zalo_is_ready
from zalo.models import ZaloOAuthToken


class Command(BaseCommand):
    help = 'Hiển thị trạng thái cấu hình Zalo OA / template OTP'

    def handle(self, *args, **options):
        enabled = getattr(settings, 'ZALO_ENABLED', False)
        app_id = (getattr(settings, 'ZALO_APP_ID', '') or '').strip()
        has_secret = bool((getattr(settings, 'ZALO_APP_SECRET', '') or '').strip())
        template_id = (getattr(settings, 'ZALO_OTP_TEMPLATE_ID', '') or '').strip()
        oa_id = (getattr(settings, 'ZALO_OA_ID', '') or '').strip()
        param = (getattr(settings, 'ZALO_OTP_TEMPLATE_PARAM', '') or 'otp').strip()
        dev = bool(getattr(settings, 'ZALO_DEVELOPMENT_MODE', True))
        env_rt = bool((getattr(settings, 'ZALO_REFRESH_TOKEN', '') or '').strip())

        self.stdout.write('=== Zalo OA / ZBS OTP ===')
        self.stdout.write(f'ZALO_ENABLED              = {enabled}')
        self.stdout.write(f'ZALO_APP_ID               = {app_id or "(empty)"}')
        self.stdout.write(f'ZALO_APP_SECRET           = {"(set)" if has_secret else "(empty)"}')
        self.stdout.write(f'ZALO_OA_ID                = {oa_id or "(optional)"}')
        self.stdout.write(f'ZALO_OTP_TEMPLATE_ID      = {template_id or "(empty)"}')
        self.stdout.write(f'ZALO_OTP_TEMPLATE_PARAM   = {param}')
        self.stdout.write(f'ZALO_DEVELOPMENT_MODE     = {dev}')
        self.stdout.write(f'ZALO_REFRESH_TOKEN (.env) = {"(set)" if env_rt else "(empty)"}')
        self.stdout.write(f'zalo_is_configured()      = {zalo_is_configured()}')
        self.stdout.write(f'zalo_has_refresh_token()  = {zalo_has_refresh_token()}')
        self.stdout.write(f'zalo_is_ready()           = {zalo_is_ready()}')

        self.stdout.write('')
        self.stdout.write('--- Token in DB (ZaloOAuthToken pk=1) ---')
        try:
            state = ZaloOAuthToken.get_solo()
        except Exception as exc:
            self.stdout.write(self.style.WARNING(
                f'Table missing or DB error: {exc}. Run: python manage.py migrate zalo'
            ))
            return

        self.stdout.write(f'access_token  = {"(set)" if state.access_token else "(empty)"}')
        self.stdout.write(f'refresh_token = {"(set)" if state.refresh_token else "(empty)"}')
        if state.expires_at:
            local = timezone.localtime(state.expires_at)
            valid = 'valid' if state.access_token_valid() else 'expired'
            self.stdout.write(f'expires_at    = {local:%Y-%m-%d %H:%M} ({valid})')
        else:
            self.stdout.write('expires_at    = (empty)')
        if state.updated_at:
            self.stdout.write(f'updated_at    = {timezone.localtime(state.updated_at):%Y-%m-%d %H:%M}')

        if not zalo_is_ready():
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('Not ready. Checklist:'))
            self.stdout.write('  1. Docs: docs/integrations/zalo/README.md')
            self.stdout.write('  2. Fill ZALO_* in .env then restart web')
            self.stdout.write('  3. Exchange auth code: python manage.py zalo_oauth_exchange --code ...')
            self.stdout.write('  4. Test: python manage.py zalo_send_test_otp --phone 09...')
            return

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Ready to send OTP (P1). Try zalo_send_test_otp.'))
        if dev:
            self.stdout.write(self.style.WARNING(
                'ZALO_DEVELOPMENT_MODE=1 — only OA/App admins receive messages.'
            ))
