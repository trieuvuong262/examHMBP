"""Kiểm tra nhanh tình trạng thư mục lưu trữ NAS cho module Báo cáo.

Dùng để: (1) hiện cảnh báo trên trang nhập báo cáo khi NAS mất kết nối,
(2) đánh dấu NAS lỗi ngay khi một lần ghi file thất bại.
Báo cáo bằng văn bản / bảng vẫn lưu bình thường vì nội dung nằm trong DB;
chỉ phần đính kèm file/ảnh mới cần NAS.
"""

from __future__ import annotations

import logging
import subprocess

from django.core.cache import cache

logger = logging.getLogger(__name__)

NAS_STORAGE_UNAVAILABLE_MSG = (
    'Kết nối thư mục lưu trữ (NAS) đang gặp sự cố. '
    'Bạn vẫn gửi được báo cáo bằng văn bản và bảng — vui lòng KHÔNG đính kèm '
    'file/ảnh lúc này và báo lại bộ phận IT để khắc phục.'
)

_CACHE_KEY = 'reports:nas_storage_available'
_CACHE_TTL_OK = 60
_CACHE_TTL_DOWN = 30
_PROBE_TIMEOUT_SEC = 3.0


def _probe_mount_responsive() -> bool:
    """Đọc thử mount — phát hiện NFS treo khi NAS mất kết nối."""
    from nas_storage.nas_paths import nas_is_available, nas_mount_root

    if not nas_is_available():
        return False

    root = str(nas_mount_root())
    try:
        proc = subprocess.run(
            ['ls', '-1', root],
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT_SEC,
            check=False,
        )
        return proc.returncode == 0
    except subprocess.TimeoutExpired:
        logger.warning('NAS mount không phản hồi trong %.1fs', _PROBE_TIMEOUT_SEC)
        return False
    except OSError:
        return False


def _probe() -> bool:
    try:
        return _probe_mount_responsive()
    except Exception:  # noqa: BLE001 - probe không được phép làm sập trang
        logger.exception('Probe NAS storage thất bại')
        return False


def report_storage_available(*, use_cache: bool = True) -> bool:
    """True nếu NAS đang sẵn sàng ghi đính kèm báo cáo (kết quả cache ngắn)."""
    if use_cache:
        cached = cache.get(_CACHE_KEY)
        if cached is not None:
            return cached
    available = _probe()
    cache.set(_CACHE_KEY, available, _CACHE_TTL_OK if available else _CACHE_TTL_DOWN)
    return available


def mark_storage_unavailable() -> None:
    """Đánh dấu NAS lỗi ngay (gọi khi một lần ghi file thất bại)."""
    cache.set(_CACHE_KEY, False, _CACHE_TTL_DOWN)
