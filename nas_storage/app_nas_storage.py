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
    allow_mount: bool = True,
) -> None:
    """Lưu file ứng dụng (báo cáo, thông báo) lên NAS.

    ``allow_mount=False``: KHÔNG đụng mount FUSE (``shutil.copyfile``) — chỉ dùng
    rclone/DSM qua mạng. Cần cho báo cáo: khi NAS vừa rớt mà mount FUSE treo (D-state),
    thao tác trên mount treo vĩnh viễn làm kẹt worker; rclone có timeout nên fail an toàn.
    """
    tmp_path = Path(tmp_path)
    mount_dest = Path(mount_dest)
    file_rel = (file_rel or '').lstrip('/')
    folder_rel_base = (folder_rel_base or '').strip('/')

    from nas_storage.nas_mount_health import mount_io_safe

    # Chỉ chạm mount khi chắc chắn không treo: mkdir/copyfile trên mount FUSE đã
    # mất kết nối sẽ kẹt D-state, không kill được bằng gunicorn --timeout.
    if allow_mount and mount_io_safe(mount_dest):
        try:
            mount_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(tmp_path, mount_dest)
            return
        except OSError:
            pass

    target = app_storage_rclone_target(folder_rel_base, file_rel)
    rclone_cmd = ['rclone', 'copyto', str(tmp_path), target]
    if not allow_mount:
        # Fail nhanh khi NAS mất kết nối để rơi về lưu tạm, không treo request.
        rclone_cmd += [
            '--contimeout', '5s',
            '--timeout', '30s',
            '--retries', '1',
            '--low-level-retries', '1',
        ]
    try:
        proc = subprocess.run(
            rclone_cmd,
            capture_output=True,
            text=True,
            # 600s cũ vượt `gunicorn --timeout 300` → worker bị kill trước khi
            # rclone hết hạn. Dùng ngân sách an toàn cho request.
            timeout=rclone_request_timeout() if allow_mount else 90,
            check=False,
            env=_rclone_env(),
        )
        rclone_err = '' if proc.returncode == 0 else (proc.stderr or proc.stdout or '').strip()
    except subprocess.TimeoutExpired:
        proc = None
        rclone_err = 'rclone timeout'
    if proc is not None and proc.returncode == 0:
        return

    full_rel = f'{folder_rel_base}/{file_rel}' if folder_rel_base and file_rel else folder_rel_base or file_rel
    try:
        dsm_upload_nas_rel(tmp_path, full_rel)
    except DsmUploadError as exc:
        raise OSError(
            f'Không ghi được file lên NAS (mount/rclone/DSM). '
            f'rclone: {rclone_err[:120] or "lỗi"}; DSM: {exc}'
        ) from exc


def rclone_request_timeout() -> int:
    """Timeout rclone cho code chạy trong request web (< gunicorn --timeout)."""
    try:
        value = int(getattr(settings, 'NAS_RCLONE_REQUEST_TIMEOUT', 120) or 120)
    except (TypeError, ValueError):
        value = 120
    return max(5, min(280, value))


def rclone_job_timeout() -> int:
    """Timeout rclone cho job nền (RQ) — không bị gunicorn giới hạn."""
    try:
        value = int(getattr(settings, 'NAS_RCLONE_JOB_TIMEOUT', 600) or 600)
    except (TypeError, ValueError):
        value = 600
    return max(30, value)


def persist_app_nas_mkdir(folder_rel_base: str) -> None:
    """Tạo thư mục gốc lưu trữ ứng dụng trên NAS (best-effort)."""
    folder_rel_base = (folder_rel_base or '').strip('/')
    if not folder_rel_base:
        return
    from nas_storage.nas_mount_health import mount_io_safe

    mount_root = Path(getattr(settings, 'NAS_MOUNT_ROOT', '/mnt/nas-portal')) / folder_rel_base
    if mount_io_safe(mount_root):
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
