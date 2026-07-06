"""Lưu tạm đính kèm/ảnh báo cáo trên VPS khi NAS mất kết nối.

Khi NAS lỗi, file/ảnh báo cáo vẫn được nhận và ghi xuống thư mục tạm trên VPS
(``MEDIA_ROOT/reports_pending/<kind>/<nas_rel_name>``). Tên file (``file.name``
trong model) vẫn là **đường dẫn NAS chuẩn** — nhờ vậy khi NAS phục hồi chỉ cần
đẩy file lên đúng vị trí rồi xóa bản tạm, không phải sửa DB.

Nguồn sự thật cho "file đang chờ đồng bộ" chính là sự tồn tại của bản tạm trên
VPS (kể cả ảnh inline CKEditor vốn không có bản ghi model riêng).
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path

from django.conf import settings

KIND_DAILY = 'daily'
KIND_WEEKLY = 'weekly'
KIND_MONTH = 'month'
_ALL_KINDS = (KIND_DAILY, KIND_WEEKLY, KIND_MONTH)

_PENDING_DIRNAME = 'reports_pending'


def pending_root(kind: str) -> Path:
    return Path(settings.MEDIA_ROOT) / _PENDING_DIRNAME / kind


def pending_path(kind: str, name: str) -> Path:
    return pending_root(kind) / (name or '').lstrip('/')


def pending_exists(kind: str, name: str) -> bool:
    if not name:
        return False
    try:
        return pending_path(kind, name).is_file()
    except OSError:
        return False


def write_pending(kind: str, name: str, tmp_path: Path) -> Path:
    """Ghi bản tạm xuống VPS; trả về đường dẫn đã ghi."""
    dest = pending_path(kind, name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(tmp_path, dest)
    return dest


def remove_pending(kind: str, name: str) -> None:
    """Xóa bản tạm trên VPS + dọn thư mục rỗng còn lại (best-effort)."""
    dest = pending_path(kind, name)
    try:
        dest.unlink(missing_ok=True)
    except OSError:
        return
    root = pending_root(kind)
    parent = dest.parent
    while parent != root and parent.is_relative_to(root):
        try:
            next(parent.iterdir())
            break
        except StopIteration:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
        except OSError:
            break


def iter_pending_names(kind: str) -> Iterator[str]:
    """Liệt kê rel name của mọi file đang chờ đồng bộ cho một loại báo cáo."""
    root = pending_root(kind)
    if not root.exists():
        return
    for path in root.rglob('*'):
        try:
            if not path.is_file():
                continue
        except OSError:
            continue
        yield path.relative_to(root).as_posix()


def count_pending(kind: str | None = None) -> int:
    kinds = (kind,) if kind else _ALL_KINDS
    return sum(1 for k in kinds for _ in iter_pending_names(k))


def has_pending(kind: str | None = None) -> bool:
    kinds = (kind,) if kind else _ALL_KINDS
    for k in kinds:
        for _ in iter_pending_names(k):
            return True
    return False
