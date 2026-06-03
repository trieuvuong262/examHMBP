"""Đường dẫn NAS an toàn — map phòng ban + account Portal."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings

from hrm.department_permission_templates import department_name_to_code
from hrm.permissions import get_profile

DEPT_SHARED_FOLDER = '_CHUNG'

# Mặc định: KD-MKT là remote gốc synology:KD-MKT (không DATACHUNG/KD-MKT)
_DEFAULT_DEPT_ROOT_REMOTES = {'KD-MKT': 'synology:KD-MKT'}


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


def user_department_folder_code(user) -> str | None:
    if not getattr(user, 'is_authenticated', False):
        return None
    from hrm.models import Profile

    dept_name = (
        Profile.objects.filter(user_id=user.pk)
        .values_list('department__name', flat=True)
        .first()
    )
    return department_folder_code(dept_name)


def dept_nas_mount_roots() -> dict[str, str]:
    """Mount local tương ứng share gốc (đọc nhanh, không qua rclone)."""
    mounts: dict[str, str] = {}
    raw = (getattr(settings, 'NAS_DEPT_MOUNT_ROOTS', '') or '').strip()
    for part in raw.split(','):
        part = part.strip()
        if ':' not in part:
            continue
        code, mpath = part.split(':', 1)
        code = code.strip().upper()
        mpath = mpath.strip()
        if code and mpath:
            mounts[code] = mpath
    return mounts


def nas_local_mount_root(user) -> Path:
    dept_code = user_department_folder_code(user)
    mounts = dept_nas_mount_roots()
    if dept_code and dept_code in mounts:
        return Path(mounts[dept_code])
    return nas_mount_root()


def dept_nas_root_remotes() -> dict[str, str]:
    """Mã phòng ban → rclone remote gốc (vd. synology:KD-MKT)."""
    remotes = dict(_DEFAULT_DEPT_ROOT_REMOTES)
    raw = (getattr(settings, 'NAS_DEPT_ROOT_REMOTES', '') or '').strip()
    for part in raw.split(','):
        part = part.strip()
        if ':' not in part:
            continue
        code, remote = part.split(':', 1)
        code = code.strip().upper()
        remote = remote.strip()
        if code and remote:
            remotes[code] = remote
    return remotes


def uses_dept_nas_root_remote(dept_code: str | None) -> bool:
    return bool(dept_code and dept_code in dept_nas_root_remotes())


def strip_legacy_dept_prefix(rel_path: str, dept_code: str | None) -> str:
    """Chuẩn hóa đường dẫn cũ KD-MKT/user → user khi phòng ban dùng remote gốc."""
    rel = normalize_rel_path(rel_path)
    if not dept_code or not uses_dept_nas_root_remote(dept_code):
        return rel
    prefix = f'{dept_code}/'
    if rel == dept_code:
        return ''
    if rel.startswith(prefix):
        return rel[len(prefix):]
    return rel


def department_default_nas_roots(user) -> list[NasRootEntry]:
    """Map mặc định: share gốc hoặc {MÃ_PB}/{username} + _CHUNG."""
    from hrm.models import Profile

    row = (
        Profile.objects.filter(user_id=user.pk)
        .values_list('department__name', 'full_name')
        .first()
    )
    if not row or not row[0]:
        return []
    dept_name, _full_name = row
    dept_code = department_folder_code(dept_name)
    if not dept_code:
        return []
    username = user.username
    if uses_dept_nas_root_remote(dept_code):
        return [
            NasRootEntry(
                key='personal',
                label='Thư mục cá nhân',
                rel_path=username,
                description=f'{dept_name} · {username}',
            ),
            NasRootEntry(
                key='dept_shared',
                label='Chung phòng ban',
                rel_path=DEPT_SHARED_FOLDER,
                description=f'Tài liệu dùng chung · {dept_name}',
            ),
        ]
    return [
        NasRootEntry(
            key='personal',
            label='Thư mục cá nhân',
            rel_path=f'{dept_code}/{username}',
            description=f'{dept_name} · {username}',
        ),
        NasRootEntry(
            key='dept_shared',
            label='Chung phòng ban',
            rel_path=f'{dept_code}/{DEPT_SHARED_FOLDER}',
            description=f'Tài liệu dùng chung · {dept_name}',
        ),
    ]


def get_user_nas_roots(user) -> list[NasRootEntry]:
    from nas_storage.user_folders import custom_roots_from_db, user_has_custom_nas_folders

    if user_has_custom_nas_folders(user):
        return custom_roots_from_db(user)
    return department_default_nas_roots(user)


def _allowed_rel_prefixes(user) -> list[str]:
    dept_code = user_department_folder_code(user)
    prefixes = []
    for entry in get_user_nas_roots(user):
        prefixes.append(strip_legacy_dept_prefix(entry.rel_path, dept_code))
    return prefixes


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
    dept_code = user_department_folder_code(user)
    rel = strip_legacy_dept_prefix(rel_path, dept_code)
    if not rel:
        raise NasPathError('Chưa chọn thư mục.')

    allowed = _allowed_rel_prefixes(user)
    if not allowed:
        raise NasPathError('Tài khoản chưa được gán phòng ban trên Portal.')

    if not any(rel == prefix or rel.startswith(prefix + '/') for prefix in allowed):
        raise NasPathError('Bạn không có quyền truy cập thư mục này.')

    mount = nas_local_mount_root(user)
    candidate = (mount / rel).resolve()
    mount_resolved = mount.resolve()
    try:
        candidate.relative_to(mount_resolved)
    except ValueError as exc:
        raise NasPathError('Đường dẫn ngoài phạm vi NAS.') from exc

    return candidate


def list_directory(
    path: Path,
    *,
    fresh: bool = False,
    rel_path: str = '',
    user=None,
) -> dict:
    listing, _source, _stale = list_directory_with_source(
        path, fresh=fresh, rel_path=rel_path, user=user,
    )
    return listing


_rclone_listing_ok: bool | None = None


def rclone_listing_available() -> bool:
    """rclone + config có sẵn để liệt kê thư mục (bỏ qua cache FUSE)."""
    global _rclone_listing_ok
    if _rclone_listing_ok is not None:
        return _rclone_listing_ok
    if not shutil.which('rclone'):
        _rclone_listing_ok = False
        return False
    config = getattr(settings, 'NAS_RCLONE_CONFIG', '')
    if config and not os.path.isfile(config):
        _rclone_listing_ok = False
        return False
    _rclone_listing_ok = True
    return True


def nas_path_exists(rel_path: str, *, user=None) -> bool:
    """Kiểm tra nhanh qua mount — không gọi rclone (tránh chậm trang gốc NAS)."""
    dept_code = user_department_folder_code(user) if user else None
    rel = strip_legacy_dept_prefix(rel_path, dept_code)
    if not rel:
        return False

    mount = nas_local_mount_root(user) if user else nas_mount_root()
    candidate = mount / rel
    try:
        return candidate.exists()
    except OSError:
        return False


def list_directory_with_source(
    path: Path,
    *,
    fresh: bool = False,
    rel_path: str = '',
    user=None,
) -> tuple[dict, str, bool]:
    """Trả về (listing, source, stale). Mặc định đọc mount (nhanh); rclone khi refresh hoặc mount trống."""
    dept_code = user_department_folder_code(user) if user else None
    rel = strip_legacy_dept_prefix(rel_path, dept_code)

    if not fresh:
        try:
            if path.is_dir():
                listing = _list_directory_local(path)
                return listing, 'mount', False
        except NasPathError:
            pass

    if rel and rclone_listing_available():
        if not fresh:
            try:
                return list_directory_via_rclone(rel, user=user, fresh=False), 'rclone', False
            except NasPathError:
                pass
        else:
            try:
                return list_directory_via_rclone(rel, user=user, fresh=True), 'rclone', False
            except NasPathError:
                raise NasPathError(
                    'Không đồng bộ được từ NAS (rclone). '
                    'Liên hệ IT kiểm tra cấu hình rclone trên server.'
                ) from None

    listing = _list_directory_local(path)
    return listing, 'mount', bool(fresh and rel)


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


def _rclone_remote_path(rel_path: str, *, user=None) -> str:
    dept_code = user_department_folder_code(user) if user else None
    rel = strip_legacy_dept_prefix(rel_path, dept_code)
    remotes = dept_nas_root_remotes()

    if dept_code and dept_code in remotes:
        base = remotes[dept_code].rstrip('/')
        return f'{base}/{rel}' if rel else base

    base = getattr(settings, 'NAS_RCLONE_REMOTE', 'synology:DATACHUNG').rstrip('/')
    kd_remote = remotes.get('KD-MKT')
    if kd_remote and rel and (rel == 'KD-MKT' or rel.startswith('KD-MKT/')):
        stripped = rel[7:].lstrip('/') if len(rel) > 6 else ''
        kd_base = kd_remote.rstrip('/')
        return f'{kd_base}/{stripped}' if stripped else kd_base

    if rel:
        return f'{base}/{rel}'
    return base


def _rclone_env() -> dict:
    env = os.environ.copy()
    config = getattr(settings, 'NAS_RCLONE_CONFIG', '')
    if config and os.path.isfile(config):
        env['RCLONE_CONFIG'] = config
    return env


def _listing_cache_key(user, rel_path: str) -> str | None:
    if not user or not getattr(user, 'pk', None):
        return None
    return f'nas:lsjson:{user.pk}:{rel_path}'


def invalidate_listing_cache(user, rel_path: str = '') -> None:
    from django.core.cache import cache

    if not user or not getattr(user, 'pk', None):
        return
    if rel_path:
        cache.delete(_listing_cache_key(user, rel_path))
        return
    prefix = f'nas:lsjson:{user.pk}:'
    try:
        cache.delete_pattern(f'{prefix}*')
    except AttributeError:
        pass


def list_directory_via_rclone(rel_path: str, *, user=None, fresh: bool = False) -> dict:
    """Đọc trực tiếp qua rclone — có cache ngắn để mở thư mục nhanh hơn."""
    dept_code = user_department_folder_code(user) if user else None
    rel = strip_legacy_dept_prefix(rel_path, dept_code)
    cache_key = _listing_cache_key(user, rel) if user and not fresh else None
    if cache_key:
        from django.core.cache import cache

        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    target = _rclone_remote_path(rel, user=user)
    timeout = int(getattr(settings, 'NAS_RCLONE_LIST_TIMEOUT', '60'))
    cmd = ['rclone', 'lsjson', target, '--no-mimetype']
    if getattr(settings, 'NAS_RCLONE_FAST_LIST', True):
        cmd.append('--fast-list')
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
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
    listing = {'folders': folders, 'files': files}
    if cache_key:
        from django.core.cache import cache

        ttl = int(getattr(settings, 'NAS_LISTING_CACHE_SECONDS', 45))
        cache.set(cache_key, listing, ttl)
    return listing


def nas_item_kind(rel_path: str, *, user=None) -> str | None:
    """'file', 'dir', hoặc None — kiểm tra mount rồi rclone."""
    dept_code = user_department_folder_code(user) if user else None
    rel = strip_legacy_dept_prefix(rel_path, dept_code)
    if not rel:
        return None

    local_root = nas_local_mount_root(user) if user else nas_mount_root()
    local = local_root / rel
    try:
        if local.is_file():
            return 'file'
        if local.is_dir():
            return 'dir'
    except OSError:
        pass

    if not rclone_listing_available():
        return None

    target = _rclone_remote_path(rel, user=user)
    try:
        proc = subprocess.run(
            ['rclone', 'lsl', target],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            env=_rclone_env(),
        )
        if proc.returncode == 0 and (proc.stdout or '').strip():
            return 'file'
        proc = subprocess.run(
            ['rclone', 'lsd', target],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            env=_rclone_env(),
        )
        if proc.returncode == 0:
            return 'dir'
    except (OSError, subprocess.TimeoutExpired):
        return None
    return None


def delete_nas_item(user, rel_path: str) -> str:
    """
    Xóa file/thư mục trên NAS (mount hoặc rclone).
    Trả về tên mục đã xóa.
    """
    dept_code = user_department_folder_code(user)
    rel = strip_legacy_dept_prefix(rel_path, dept_code)
    if not rel:
        raise NasPathError('Chưa chọn mục cần xóa.')

    kind = nas_item_kind(rel, user=user)
    name = Path(rel).name
    if kind is None:
        raise NasPathError('Không tìm thấy file hoặc thư mục trên NAS.')

    local = nas_local_mount_root(user) / rel

    if kind == 'file':
        try:
            if local.is_file():
                local.unlink()
                return name
        except OSError:
            pass
        delete_via_rclone(rel, user=user)
        return name

    if kind == 'dir':
        try:
            if local.is_dir():
                if any(local.iterdir()):
                    raise NasPathError('Chỉ xóa được thư mục rỗng.')
                local.rmdir()
                return name
        except NasPathError:
            raise
        except OSError:
            pass
        listing = list_directory_via_rclone(rel, user=user, fresh=True)
        if listing['folders'] or listing['files']:
            raise NasPathError('Chỉ xóa được thư mục rỗng.')
        delete_dir_via_rclone(rel, user=user)
        return name

    raise NasPathError('Không tìm thấy file hoặc thư mục trên NAS.')


def delete_via_rclone(rel_path: str, *, user=None) -> None:
    target = _rclone_remote_path(rel_path, user=user)
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


def delete_dir_via_rclone(rel_path: str, *, user=None) -> None:
    target = _rclone_remote_path(rel_path, user=user)
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


def build_breadcrumb(rel_path: str, *, user=None) -> list[dict]:
    dept_code = user_department_folder_code(user) if user else None
    rel = strip_legacy_dept_prefix(rel_path, dept_code)
    if not rel:
        return []
    crumbs = [{'label': 'Thư mục NAS', 'rel_path': ''}]
    parts = rel.split('/')
    acc = []
    for part in parts:
        acc.append(part)
        crumbs.append({'label': part, 'rel_path': '/'.join(acc)})
    return crumbs
