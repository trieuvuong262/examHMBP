"""Đọc/ghi công tắc quét virus file upload.

Nguồn sự thật là DB (``FileScanConfig``) để IT bật/tắt ngay trên portal, không
phải sửa ``.env`` rồi deploy lại. ``.env`` giữ hai vai trò:

* ``AV_SCAN_ENABLED`` — giá trị khởi tạo lần đầu, và quyết định container
  ``clamav`` có được khởi động lúc deploy hay không (nó chiếm ~2GB RAM).
* ``AV_SCAN_FORCE_OFF`` — cầu dao khẩn cấp: bật lên là tắt quét bất kể DB nói
  gì, dùng khi scanner gây sự cố mà không vào được portal.
"""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def force_off() -> bool:
    """Cầu dao khẩn cấp trong .env — thắng mọi cấu hình DB."""
    return bool(getattr(settings, 'AV_SCAN_FORCE_OFF', False))


def get_config():
    """Bản ghi cấu hình (memo hoá trong 1 request đọc)."""
    from audit.models import FileScanConfig
    from hrm.request_cache import get_or_set

    return get_or_set(('file_scan_config',), FileScanConfig.get_solo)


def _config_or_none():
    """Trả config, None nếu DB chưa sẵn sàng (migrate, test không có bảng)."""
    try:
        return get_config()
    except Exception:  # noqa: BLE001 - không để cấu hình làm sập luồng upload
        logger.debug('Chưa đọc được FileScanConfig — dùng giá trị .env', exc_info=True)
        return None


def scan_enabled() -> bool:
    if force_off():
        return False
    config = _config_or_none()
    if config is None:
        return bool(getattr(settings, 'AV_SCAN_ENABLED', False))
    return bool(config.enabled)


def scan_fail_closed() -> bool:
    config = _config_or_none()
    if config is None:
        return bool(getattr(settings, 'AV_FAIL_CLOSED', False))
    return bool(config.fail_closed)


def save_config(*, enabled: bool, fail_closed: bool, admin_user):
    """Lưu công tắc; trả bản ghi đã cập nhật."""
    from hrm.request_cache import invalidate

    config = get_config()
    config.enabled = bool(enabled)
    config.fail_closed = bool(fail_closed)
    config.updated_by = admin_user if getattr(admin_user, 'is_authenticated', False) else None
    config.save(update_fields=['enabled', 'fail_closed', 'updated_by', 'updated_at'])
    invalidate('file_scan_config')
    return config


def scanner_status() -> dict:
    """Trạng thái scanner để hiển thị trên màn hình cấu hình."""
    from nas_storage.av_scan import ping, version

    alive = ping()
    return {
        'alive': alive,
        'version': version() if alive else '',
        'host': getattr(settings, 'AV_CLAMD_HOST', ''),
        'port': getattr(settings, 'AV_CLAMD_PORT', ''),
        'container_enabled': bool(getattr(settings, 'AV_SCAN_ENABLED', False)),
        'force_off': force_off(),
    }
