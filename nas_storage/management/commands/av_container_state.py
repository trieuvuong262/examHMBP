"""In trạng thái mong muốn của container ClamAV — cho deploy.sh đọc.

    docker compose exec -T web python manage.py av_container_state
    -> in "on", "off", hoặc "unknown"

Nguồn sự thật là công tắc trong DB (Nhật ký → Bảo mật đăng nhập → Quét virus
file), nên bật/tắt không cần SSH sửa .env nữa. ``AV_SCAN_FORCE_OFF`` trong .env
vẫn thắng để còn cầu dao khẩn cấp.

``unknown`` = chưa đọc được DB/web — deploy.sh phải GIỮ NGUYÊN container
(không được stop clamav), tránh tắt nhầm scanner đang chạy.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'In "on"/"off"/"unknown" theo công tắc quét virus (dùng cho deploy.sh).'

    def handle(self, *args, **options):
        try:
            from audit.file_scan_config import force_off, get_config

            if force_off():
                self.stdout.write('off')
                return
            self.stdout.write('on' if get_config().enabled else 'off')
        except Exception:  # noqa: BLE001 - deploy không được vỡ vì lệnh này
            # Không mặc định "off": lần deploy trước đã stop clamav nhầm khi web
            # chưa sẵn / đọc DB lỗi → portal báo bật công tắc mà không quét được.
            self.stdout.write('unknown')
