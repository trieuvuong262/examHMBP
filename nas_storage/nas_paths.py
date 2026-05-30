"""Đường dẫn NAS an toàn — map phòng ban + account Portal."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings

from hrm.department_permission_templates import department_name_to_code
from hrm.permissions import get_profile

DEPT_SHARED_FOLDER = '_CHUNG'


@dataclass(frozen=True)
class NasRootEntry:
    key: str
    label: str
    rel_path: str
    description: str


class NasPathError(PermissionError):
    pass


def nas_mount_root() -> Path:
    return Path(getattr(settings, 'NAS_MOUNT_ROOT', '/mnt/nas-portal'))


def nas_is_available() -> bool:
    root = nas_mount_root()
    return root.is_dir() and os.access(root, os.R_OK)


def department_folder_code(department_name: str | None) -> str | None:
    if not department_name:
        return None
    code = department_name_to_code(department_name)
    if code:
        return code.upper()
    slug = department_name.strip().upper().replace(' ', '-')
    return slug or None


def get_user_nas_roots(user) -> list[NasRootEntry]:
    profile = get_profile(user)
    if not profile or not profile.department:
        return []
    dept_code = department_folder_code(profile.department.name)
    if not dept_code:
        return []
    username = user.username
    roots = [
        NasRootEntry(
            key='personal',
            label='Thư mục cá nhân',
            rel_path=f'{dept_code}/{username}',
            description=f'{profile.department.name} · {username}',
        ),
        NasRootEntry(
            key='dept_shared',
            label='Chung phòng ban',
            rel_path=f'{dept_code}/{DEPT_SHARED_FOLDER}',
            description=f'Tài liệu dùng chung · {profile.department.name}',
        ),
    ]
    return roots


def _allowed_rel_prefixes(user) -> list[str]:
    return [entry.rel_path for entry in get_user_nas_roots(user)]


def normalize_rel_path(raw: str) -> str:
    raw = (raw or '').strip().strip('/')
    if not raw:
        return ''
    parts = []
    for part in raw.replace('\\', '/').split('/'):
        part = part.strip()
        if not part or part == '.':
            continue
        if part == '..':
            raise NasPathError('Đường dẫn không hợp lệ.')
        parts.append(part)
    return '/'.join(parts)


def resolve_nas_path(user, rel_path: str) -> Path:
    rel = normalize_rel_path(rel_path)
    if not rel:
        raise NasPathError('Chưa chọn thư mục.')

    allowed = _allowed_rel_prefixes(user)
    if not allowed:
        raise NasPathError('Tài khoản chưa được gán phòng ban trên Portal.')

    if not any(rel == prefix or rel.startswith(prefix + '/') for prefix in allowed):
        raise NasPathError('Bạn không có quyền truy cập thư mục này.')

    mount = nas_mount_root()
    candidate = (mount / rel).resolve()
    mount_resolved = mount.resolve()
    try:
        candidate.relative_to(mount_resolved)
    except ValueError as exc:
        raise NasPathError('Đường dẫn ngoài phạm vi NAS.') from exc

    return candidate


def list_directory(path: Path, *, fresh: bool = False, rel_path: str = '') -> dict:
    listing, _source, _stale = list_directory_with_source(path, fresh=fresh, rel_path=rel_path)
    return listing


def list_directory_with_source(path: Path, *, fresh: bool = False, rel_path: str = '') -> tuple[dict, str, bool]:
    """Trả về (listing, source, stale). stale=True khi cần fresh nhưng chỉ đọc được qua mount."""
    if fresh and rel_path:
        try:
            return list_directory_via_rclone(rel_path), 'rclone', False
        except NasPathError:
            pass
    return _list_directory_local(path), 'mount', bool(fresh and rel_path)


def listing_fingerprint(listing: dict) -> str:
    parts = []
    for folder in listing.get('folders', []):
        parts.append(f"d:{folder['name']}:{folder.get('modified', 0)}")
    for file in listing.get('files', []):
        parts.append(f"f:{file['name']}:{file.get('size', 0)}:{file.get('modified', 0)}")
    parts.sort()
    digest = hashlib.sha256('|'.join(parts).encode('utf-8')).hexdigest()
    return digest[:16]


def _list_directory_local(path: Path) -> dict:
    if not path.is_dir():
        raise NasPathError('Thư mục không tồn tại.')

    folders = []
    files = []
    for entry in sorted(path.iterdir(), key=lambda p: p.name.lower()):
        if entry.name.startswith('.'):
            continue
        stat = entry.stat()
        item = {
            'name': entry.name,
            'size': stat.st_size,
            'modified': stat.st_mtime,
            'is_dir': entry.is_dir(),
        }
        if entry.is_dir():
            folders.append(item)
        else:
            item['mime'] = mimetypes.guess_type(entry.name)[0] or 'application/octet-stream'
            files.append(item)
    return {'folders': folders, 'files': files}


def _rclone_remote_path(rel_path: str) -> str:
    base = getattr(settings, 'NAS_RCLONE_REMOTE', 'synology:DATACHUNG').rstrip('/')
    rel = normalize_rel_path(rel_path)
    if rel:
        return f'{base}/{rel}'
    return base


def _rclone_env() -> dict:
    env = os.environ.copy()
    config = getattr(settings, 'NAS_RCLONE_CONFIG', '')
    if config and os.path.isfile(config):
        env['RCLONE_CONFIG'] = config
    return env


def list_directory_via_rclone(rel_path: str) -> dict:
    """Đọc trực tiếp qua rclone — bỏ qua cache FUSE mount."""
    target = _rclone_remote_path(rel_path)
    try:
        proc = subprocess.run(
            ['rclone', 'lsjson', target, '--dirs-first'],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
            env=_rclone_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise NasPathError('Không kết nối được NAS để đồng bộ.') from exc

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or '').strip()
        raise NasPathError(err or 'Không đọc được thư mục từ NAS.')

    try:
        rows = json.loads(proc.stdout or '[]')
    except json.JSONDecodeError as exc:
        raise NasPathError('Phản hồi NAS không hợp lệ.') from exc

    folders = []
    files = []
    for row in rows:
        name = row.get('Name') or row.get('name') or ''
        if not name or name.startswith('.'):
            continue
        is_dir = bool(row.get('IsDir') or row.get('IsDirectory'))
        mod = row.get('ModTime') or row.get('Modified')
        modified = 0.0
        if mod:
            try:
                modified = datetime.fromisoformat(mod.replace('Z', '+00:00')).timestamp()
            except ValueError:
                modified = 0.0
        item = {
            'name': name,
            'size': int(row.get('Size') or row.get('size') or 0),
            'modified': modified,
            'is_dir': is_dir,
        }
        if is_dir:
            folders.append(item)
        else:
            item['mime'] = mimetypes.guess_type(name)[0] or 'application/octet-stream'
            files.append(item)

    folders.sort(key=lambda x: x['name'].lower())
    files.sort(key=lambda x: x['name'].lower())
    return {'folders': folders, 'files': files}


def delete_via_rclone(rel_path: str) -> None:
    target = _rclone_remote_path(rel_path)
    try:
        proc = subprocess.run(
            ['rclone', 'deletefile', target],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
            env=_rclone_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise NasPathError('Không xóa được file trên NAS.') from exc
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or '').strip()
        raise NasPathError(err or 'Không xóa được file trên NAS.')


def delete_dir_via_rclone(rel_path: str) -> None:
    target = _rclone_remote_path(rel_path)
    try:
        proc = subprocess.run(
            ['rclone', 'rmdir', target],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
            env=_rclone_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise NasPathError('Không xóa được thư mục trên NAS.') from exc
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or '').strip()
        raise NasPathError(err or 'Không xóa được thư mục trên NAS.')


def listing_synced_at() -> str:
    return datetime.now(timezone.utc).astimezone().strftime('%H:%M:%S')


def build_breadcrumb(rel_path: str) -> list[dict]:
    rel = normalize_rel_path(rel_path)
    if not rel:
        return []
    crumbs = [{'label': 'Thư mục NAS', 'rel_path': ''}]
    parts = rel.split('/')
    acc = []
    for part in parts:
        acc.append(part)
        crumbs.append({'label': part, 'rel_path': '/'.join(acc)})
    return crumbs
