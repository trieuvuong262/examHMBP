"""Gửi thử OTP ZBS tới một SĐT (P1 — kiểm tra template + token).

Usage:
    python manage.py zalo_send_test_otp --phone 0912345678
    python manage.py zalo_send_test_otp --phone 0912345678 --otp 654321 --production
"""

from django.core.management.base import BaseCommand, CommandError

from hrm.phone import format_phone_vn, is_valid_vn_mobile, normalize_phone
from zalo.client import ZaloAPIError, ZaloClient, zalo_is_ready


class Command(BaseCommand):
    help = 'Gửi thử OTP qua Zalo ZBS template'

    def add_arguments(self, parser):
        parser.add_argument('--phone', required=True, help='SĐT nhận (0… hoặc 84…)')
        parser.add_argument('--otp', default='123456', help='Mã OTP thử (mặc định 123456)')
        parser.add_argument(
            '--production',
            action='store_true',
            help='Gửi thật (bỏ mode=development). Tốn phí ZBS.',
        )

    def handle(self, *args, **options):
        if not zalo_is_ready():
            raise CommandError('Zalo chưa sẵn sàng. Chạy python manage.py zalo_status.')

        phone = normalize_phone(options['phone'])
        if not is_valid_vn_mobile(phone):
            raise CommandError(f'SĐT không hợp lệ: {options["phone"]!r}')

        otp = (options['otp'] or '').strip()
        if not otp.isdigit() or not (4 <= len(otp) <= 8):
            raise CommandError('OTP phải là 4–8 chữ số.')

        development = not options['production']
        self.stdout.write(
            f'Gửi OTP {otp} → {format_phone_vn(phone)} '
            f'({"development" if development else "PRODUCTION"})…'
        )
        try:
            payload = ZaloClient().send_otp(
                phone=phone,
                otp=otp,
                development=development,
                tracking_id=f'jp-test-{phone[-4:]}',
            )
        except ZaloAPIError as exc:
            detail = ''
            if exc.payload:
                detail = f' | payload={exc.payload!r}'
            raise CommandError(f'{exc}{detail}') from exc

        self.stdout.write(self.style.SUCCESS('OK — Zalo chấp nhận request.'))
        data = payload.get('data') if isinstance(payload, dict) else None
        if isinstance(data, dict) and data.get('msg_id'):
            self.stdout.write(f'msg_id = {data["msg_id"]}')
        else:
            self.stdout.write(f'response = {payload!r}')
