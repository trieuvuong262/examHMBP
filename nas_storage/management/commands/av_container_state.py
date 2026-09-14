"""In trạng thái mong muốn của container ClamAV — cho deploy.sh đọc.

    docker compose exec -T web python manage.py av_container_state
    -> in "on" hoặc "off"

Nguồn sự thật là công tắc trong DB (Nhật ký → Bảo mật đăng nhập → Quét virus
file), nên bật/tắt không cần SSH sửa .env nữa. ``AV_SCAN_FORCE_OFF`` trong .env
vẫn thắng để còn cầu dao khẩn cấp.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'In "on"/"off" theo công tắc quét virus trong DB (dùng cho deploy.sh).'

    def handle(self, *args, **options):
        try:
            from audit.file_scan_config import force_off, get_config

            if force_off():
                self.stdout.write('off')
                return
            self.stdout.write('on' if get_config().enabled else 'off')
        except Exception:  # noqa: BLE001 - deploy không được vỡ vì lệnh này
            # DB chưa migrate hoặc lỗi đọc — coi như tắt, an toàn hơn là bật
            # một container 2GB ngoài ý muốn.
            self.stdout.write('off')
