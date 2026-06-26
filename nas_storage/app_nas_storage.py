"""Ghi file lên NAS: mount → rclone → DSM File Station."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from django.conf import settings

from nas_storage.dsm_upload import DsmUploadError, dsm_upload_nas_rel
from nas_storage.nas_paths import _rclone_env, app_storage_rclone_target


def persist_app_nas_file(
    *,
    tmp_path: Path,
    mount_dest: Path,
    folder_rel_base: str,
    file_rel: str,
) -> None:
    """Lưu file ứng dụng (báo cáo, thông báo) lên NAS."""
    tmp_path = Path(tmp_path)
    mount_dest = Path(mount_dest)
    file_rel = (file_rel or '').lstrip('/')
    folder_rel_base = (folder_rel_base or '').strip('/')

    try:
        mount_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(tmp_path, mount_dest)
        return
    except OSError:
        pass

    target = app_storage_rclone_target(folder_rel_base, file_rel)
    proc = subprocess.run(
        ['rclone', 'copyto', str(tmp_path), target],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
        env=_rclone_env(),
    )
    if proc.returncode == 0:
        return

    rclone_err = (proc.stderr or proc.stdout or '').strip()
    full_rel = f'{folder_rel_base}/{file_rel}' if folder_rel_base and file_rel else folder_rel_base or file_rel
    try:
        dsm_upload_nas_rel(tmp_path, full_rel)
    except DsmUploadError as exc:
        raise OSError(
            f'Không ghi được file lên NAS (mount/rclone/DSM). '
            f'rclone: {rclone_err[:120] or "lỗi"}; DSM: {exc}'
        ) from exc


def persist_app_nas_mkdir(folder_rel_base: str) -> None:
    """Tạo thư mục gốc lưu trữ ứng dụng trên NAS (best-effort)."""
    folder_rel_base = (folder_rel_base or '').strip('/')
    if not folder_rel_base:
        return
    mount_root = Path(getattr(settings, 'NAS_MOUNT_ROOT', '/mnt/nas-portal')) / folder_rel_base
    try:
        mount_root.mkdir(parents=True, exist_ok=True)
        return
    except OSError:
        pass
    target = app_storage_rclone_target(folder_rel_base, '')
    proc = subprocess.run(
        ['rclone', 'mkdir', target.rstrip('/')],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=_rclone_env(),
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or '').strip()
        raise OSError(f'Không tạo được thư mục trên NAS: {err[:200]}')
