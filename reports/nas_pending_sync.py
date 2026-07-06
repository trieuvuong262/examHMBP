"""Đồng bộ file báo cáo lưu tạm trên VPS lên NAS, rồi xóa bản tạm.

Chạy được từ: nút bấm trên giao diện, lệnh ``manage.py sync_nas_pending``,
hoặc tự động (best-effort) khi tải lại trang báo cáo lúc NAS đã phục hồi.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from django.core.cache import cache

from reports.daily_nas_storage import (
    daily_report_nas_abs_root,
    daily_report_nas_rel_base,
    monthly_report_nas_abs_root,
    monthly_report_nas_rel_base,
)
from reports.nas_health import mark_storage_unavailable, report_storage_available
from reports.nas_pending import (
    KIND_DAILY,
    KIND_MONTH,
    KIND_WEEKLY,
    count_pending,
    iter_pending_names,
    pending_path,
    remove_pending,
)
from reports.weekly_nas_storage import weekly_report_nas_abs_root, weekly_report_nas_rel_base

logger = logging.getLogger(__name__)

_AUTO_SYNC_LOCK_KEY = 'reports:nas_pending_auto_sync'
_AUTO_SYNC_THROTTLE_SEC = 120


def _nas_target_for(kind: str, name: str):
    if kind == KIND_WEEKLY:
        return weekly_report_nas_abs_root() / name.lstrip('/'), weekly_report_nas_rel_base()
    if kind == KIND_MONTH:
        return monthly_report_nas_abs_root() / name.lstrip('/'), monthly_report_nas_rel_base()
    return daily_report_nas_abs_root() / name.lstrip('/'), daily_report_nas_rel_base()


def _upload_one(kind: str, name: str) -> None:
    from nas_storage.app_nas_storage import persist_app_nas_file

    src = pending_path(kind, name)
    if not src.is_file():
        return
    mount_dest, rel_base = _nas_target_for(kind, name)
    persist_app_nas_file(
        tmp_path=Path(src),
        mount_dest=mount_dest,
        folder_rel_base=rel_base,
        file_rel=name,
    )
    remove_pending(kind, name)


def sync_all_pending() -> dict:
    """Đẩy mọi file tạm lên NAS. Dừng sớm nếu NAS mất kết nối giữa chừng."""
    stats = {'status': 'ok', 'synced': 0, 'failed': 0, 'errors': []}

    if not report_storage_available():
        stats['status'] = 'nas_down'
        return stats

    for kind in (KIND_DAILY, KIND_WEEKLY, KIND_MONTH):
        for name in list(iter_pending_names(kind)):
            try:
                _upload_one(kind, name)
                stats['synced'] += 1
            except OSError as exc:
                stats['failed'] += 1
                stats['errors'].append(f'{kind}/{name}: {exc}')
                logger.warning('Đồng bộ NAS thất bại %s/%s: %s', kind, name, exc)
                mark_storage_unavailable()
                stats['status'] = 'nas_down'
                return stats
    return stats


def maybe_auto_sync() -> None:
    """Kích hoạt đồng bộ nền (throttle) khi NAS sẵn sàng và còn file chờ.

    An toàn để gọi ở mỗi lần tải trang báo cáo — có khóa cache để không chạy
    trùng và chỉ chạy khi thực sự có việc.
    """
    try:
        if not count_pending():
            return
        if not cache.add(_AUTO_SYNC_LOCK_KEY, '1', _AUTO_SYNC_THROTTLE_SEC):
            return
        if not report_storage_available():
            return
    except Exception:  # noqa: BLE001 - không để tác vụ nền làm hỏng request
        logger.exception('maybe_auto_sync: lỗi khi kiểm tra điều kiện')
        return

    def _worker():
        try:
            result = sync_all_pending()
            if result.get('synced'):
                logger.info('Auto-sync NAS: đã đồng bộ %s file', result['synced'])
        except Exception:  # noqa: BLE001
            logger.exception('Auto-sync NAS thất bại')

    threading.Thread(target=_worker, name='reports-nas-auto-sync', daemon=True).start()
