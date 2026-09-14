"""Kiểm tra trạng thái quét virus (ClamAV) — dùng khi deploy và khi có sự cố.

    docker compose exec web python manage.py av_status
    docker compose exec web python manage.py av_status --eicar
"""

from __future__ import annotations

import io

from django.core.management.base import BaseCommand

from nas_storage.av_scan import av_enabled, av_fail_closed, ping, scan_stream, version

# Chuỗi thử chuẩn EICAR — mọi antivirus phải nhận diện. Ghép từ nhiều phần để
# chính file nguồn này không bị antivirus trên máy dev cách ly.
EICAR = (
    b'X5O!P%@AP[4\\PZX54(P^)7CC)7}'
    + b'$EICAR-STANDARD-ANTIVIRUS-TEST-FILE'
    + b'!$H+H*'
)


class Command(BaseCommand):
    help = 'Kiểm tra kết nối và khả năng phát hiện của ClamAV.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--eicar',
            action='store_true',
            help='Gửi chuỗi thử EICAR để xác nhận scanner thực sự phát hiện được.',
        )

    def handle(self, *args, **options):
        from django.conf import settings

        host = getattr(settings, 'AV_CLAMD_HOST', '')
        port = getattr(settings, 'AV_CLAMD_PORT', '')

        self.stdout.write('=== Trạng thái quét virus ===')
        self.stdout.write(f'  AV_SCAN_ENABLED : {av_enabled()}')
        self.stdout.write(f'  clamd           : {host}:{port}')
        self.stdout.write(f'  AV_FAIL_CLOSED  : {av_fail_closed()}')

        if not av_enabled():
            self.stdout.write(self.style.WARNING(
                '  → Đang TẮT. Đặt AV_SCAN_ENABLED=1 trong .env để bật.',
            ))

        alive = ping()
        if alive:
            self.stdout.write(self.style.SUCCESS('  PING            : PONG'))
            self.stdout.write(f'  VERSION         : {version()}')
        else:
            self.stdout.write(self.style.ERROR('  PING            : không phản hồi'))
            self.stdout.write(
                '  → Kiểm tra: docker compose ps clamav / logs clamav\n'
                '     Lần đầu freshclam tải ~250MB signature, mất vài phút.',
            )

        if not options['eicar']:
            return

        self.stdout.write('')
        self.stdout.write('=== Thử EICAR ===')
        if not av_enabled():
            self.stdout.write(self.style.WARNING('  Bỏ qua: AV_SCAN_ENABLED=0'))
            return

        result = scan_stream(io.BytesIO(EICAR), size=len(EICAR))
        if result.is_infected:
            self.stdout.write(self.style.SUCCESS(
                f'  PHÁT HIỆN ĐÚNG: {result.signature}',
            ))
        elif result.is_clean:
            self.stdout.write(self.style.ERROR(
                '  SAI: EICAR bị báo là sạch — scanner không hoạt động đúng.',
            ))
        else:
            self.stdout.write(self.style.ERROR(
                f'  Không quét được: {result.status} — {result.detail}',
            ))
