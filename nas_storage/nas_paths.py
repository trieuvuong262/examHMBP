"""Đường dẫn NAS an toàn — map phòng ban + account Portal."""

from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings

from hrm.department_permission_templates import department_name_to_code
from hrm.permissions import get_profile

logger = logging.getLogger(__name__)

DEPT_SHARED_FOLDER = '_CHUNG'

# Mặc định: KD-MKT là remote gốc synology:KD-MKT (không DATACHUNG/KD-MKT)
_DEFAULT_DEPT_ROOT_REMOTES = {'KD-MKT': 'synology:KD-MKT'}

# Thư mục hệ thống Synology — stat() dễ PermissionError trên FUSE → 500 cả trang.
_SYNOLOGY_SKIP_NAMES = frozenset({
    '#recycle',
    '#snapshot',
    '@eadir',
    '@tmp',
    '@synoeastream',
    '@sharesnap',
})


def _is_hidden_nas_name(name: str) -> bool:
    n = (name or '').strip()
    if not n or n.startswith('.'):
        return True
    lower = n.lower()
    if lower in _SYNOLOGY_SKIP_NAMES or lower.startswith('@'):
        return True
    return False


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


def nas_rclone_remote_path(base: str, rel_path: str = '') -> str:
    """Ghép remote rclone — hỗ trợ gốc share ``synology:`` (không còn DATACHUNG)."""
    base = (base or 'synology:').strip()
    rel = (rel_path or '').strip().strip('/')
    if base.endswith(':'):
        return f'{base}{rel}' if rel else base
    base = base.rstrip('/')
    return f'{base}/{rel}' if rel else base


def default_nas_rclone_remote() -> str:
    return getattr(settings, 'NAS_RCLONE_REMOTE', 'synology:').strip() or 'synology:'


def app_storage_rclone_target(folder_rel_base: str, file_rel: str) -> str:
    """rclone copyto target cho lưu trữ app (báo cáo, thông báo) trên share 99_LUU_TRU."""
    remote = default_nas_rclone_remote()
    folder = (folder_rel_base or '').strip('/')
    rel = (file_rel or '').strip('/')
    if folder and rel:
        return nas_rclone_remote_path(remote, f'{folder}/{rel}')
    if folder:
        return nas_rclone_remote_path(remote, folder)
    return nas_rclone_remote_path(remote, rel)


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


def split_share_prefixed_path(rel_path: str) -> tuple[str | None, str]:
    """
    Tách share NAS ở segment đầu (vd. 05_MARKETING/lvanhthu).
    Trả về (share_name, path_inside_share) hoặc (None, rel_path đầy đủ).
    """
    rel = normalize_rel_path(rel_path)
    if not rel:
        return None, ''
    first, _, rest = rel.partition('/')
    if first in known_nas_share_names():
        return first, rest
    return None, rel


def nas_mount_base_and_rel(user, rel_path: str) -> tuple[Path, str]:
    """
    Chọn mount + đường dẫn tương đối.
    Share chéo (05_MARKETING/…) → gốc /mnt/nas-portal, không gắn vào mount phòng ban.
    """
    dept_code = user_department_folder_code(user)
    rel = strip_legacy_dept_prefix(rel_path, dept_code)
    share_name, inner = split_share_prefixed_path(rel)
    if share_name:
        full_rel = share_name if not inner else f'{share_name}/{inner}'
        return nas_mount_root(), full_rel
    return nas_local_mount_root(user), rel


def known_nas_share_names() -> frozenset[str]:
    """Share tĩnh (phòng ban) + share đã đăng ký trên Portal (00_, 80_, 90_, …)."""
    from nas_storage.dept_nas_config import known_nas_share_names as _static

    names = set(_static())
    try:
        from nas_storage.models import NasShareFolder

        names.update(
            NasShareFolder.objects.filter(is_active=True)
            .exclude(share_name='')
            .values_list('share_name', flat=True)
            .distinct()
        )
    except Exception:
        pass
    return frozenset(names)


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
    from nas_storage.portal_access import (
        all_share_portal_roots,
        portal_roots_from_folder_permissions,
        user_has_portal_browse_all,
    )
    from nas_storage.user_folders import custom_roots_from_db, user_has_custom_nas_folders

    if user_has_custom_nas_folders(user):
        return custom_roots_from_db(user)
    if user_has_portal_browse_all(user):
        return all_share_portal_roots()
    permission_roots = portal_roots_from_folder_permissions(user)
    if permission_roots:
        return permission_roots
    return []


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


_VOLUME_PATH_RE = re.compile(r'(/volume\d+/[A-Za-z0-9_./-]+)', re.I)


def normalize_volume_path(raw: str, *, share_name: str = '') -> str:
    """Chuẩn hoá đường dẫn volume DSM — bỏ tiền tố thừa (vd. «VD:»)."""
    text = (raw or '').strip()
    share = (share_name or '').strip()
    if not text:
        if not share:
            return ''
        return f'/volume1/{share}'
    match = _VOLUME_PATH_RE.search(text.replace('\\', '/'))
    if match:
        return match.group(1).rstrip('/')
    if text.startswith('/volume'):
        return text.rstrip('/')
    if share:
        return f'/volume1/{share}'
    raise NasPathError(f'Đường dẫn volume không hợp lệ: {raw}')


def resolve_nas_path(user, rel_path: str) -> Path:
    from nas_storage.dept_nas_config import is_portal_browse_hidden_share

    dept_code = user_department_folder_code(user)
    rel = strip_legacy_dept_prefix(rel_path, dept_code)
    if not rel:
        raise NasPathError('Chưa chọn thư mục.')

    first_seg = rel.split('/', 1)[0]
    if is_portal_browse_hidden_share(first_seg):
        raise NasPathError('Bạn không có quyền truy cập thư mục này.')

    allowed = _allowed_rel_prefixes(user)
    if not allowed:
        raise NasPathError('Tài khoản chưa được gán phòng ban trên Portal.')

    if not any(rel == prefix or rel.startswith(prefix + '/') for prefix in allowed):
        raise NasPathError('Bạn không có quyền truy cập thư mục này.')

    from nas_storage.user_folder_privacy import user_can_access_private_nas_rel

    if not user_can_access_private_nas_rel(user, rel):
        raise NasPathError('Bạn không có quyền truy cập thư mục này.')

    mount, rel = nas_mount_base_and_rel(user, rel_path)
    candidate = (mount / rel).resolve() if rel else mount.resolve()
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

    mount, rel = nas_mount_base_and_rel(user, rel_path) if user else (nas_mount_root(), rel)
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
                listing = _apply_listing_privacy(user, rel, _list_directory_local(path))
                return listing, 'mount', False
        except NasPathError:
            pass
        except OSError:
            logger.warning('NAS mount list failed for %s', path, exc_info=True)

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

    listing = _apply_listing_privacy(user, rel, _list_directory_local(path))
    return listing, 'mount', bool(fresh and rel)


def listing_fingerprint(listing: dict) -> str:
    parts = []
    for folder in listing.get('folders', []):
        parts.append(f"d:{folder['name']}:{folder.get('modified', 0)}")
    for file in listing.get('files', []):
        parts.append(f"f:{file['name']}:{file.get('size', 0)}:{file.get('modified', 0)}")
    parts.sort()
    digest = hashlib.sha256('|'.join(parts).encode('utf-8', 'replace')).hexdigest()
    return digest[:16]


def _list_directory_local(path: Path) -> dict:
    try:
        if not path.is_dir():
            raise NasPathError('Thư mục không tồn tại.')
        entries = list(path.iterdir())
    except NasPathError:
        raise
    except OSError as exc:
        raise NasPathError('Không đọc được thư mục trên NAS.') from exc

    try:
        entries.sort(key=lambda p: p.name.lower())
    except Exception:
        entries.sort(key=lambda p: p.name.encode('utf-8', 'replace'))

    folders = []
    files = []
    for entry in entries:
        if _is_hidden_nas_name(entry.name):
            continue
        try:
            stat = entry.stat()
            is_dir = entry.is_dir()
        except OSError as exc:
            logger.warning('NAS skip entry %s: %s', entry, exc)
            continue
        item = {
            'name': entry.name,
            'size': stat.st_size,
            'modified': stat.st_mtime,
            'is_dir': is_dir,
        }
        if is_dir:
            folders.append(item)
        else:
            item['mime'] = mimetypes.guess_type(entry.name)[0] or 'application/octet-stream'
            files.append(item)
    return {'folders': folders, 'files': files}


def _apply_listing_privacy(user, rel_path: str, listing: dict) -> dict:
    if user is None:
        return listing
    from nas_storage.user_folder_privacy import filter_listing_folders_for_user

    return {
        'folders': filter_listing_folders_for_user(user, rel_path, listing.get('folders', [])),
        'files': listing.get('files', []),
    }


def _rclone_remote_path(rel_path: str, *, user=None) -> str:
    dept_code = user_department_folder_code(user) if user else None
    rel = strip_legacy_dept_prefix(rel_path, dept_code)
    share_name, inner = split_share_prefixed_path(rel)
    if share_name:
        return nas_rclone_remote_path(f'synology:{share_name}', inner)

    remotes = dept_nas_root_remotes()

    if dept_code and dept_code in remotes:
        base = remotes[dept_code].rstrip('/')
        return f'{base}/{rel}' if rel else base

    base = default_nas_rclone_remote()
    kd_remote = remotes.get('KD-MKT')
    if kd_remote and rel and (rel == 'KD-MKT' or rel.startswith('KD-MKT/')):
        stripped = rel[7:].lstrip('/') if len(rel) > 6 else ''
        return nas_rclone_remote_path(kd_remote, stripped)

    return nas_rclone_remote_path(base, rel)


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
        if _is_hidden_nas_name(name):
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
    if user is not None:
        from nas_storage.user_folder_privacy import filter_listing_folders_for_user

        listing['folders'] = filter_listing_folders_for_user(user, rel, listing['folders'])
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

    local_root, rel = nas_mount_base_and_rel(user, rel_path) if user else (nas_mount_root(), rel)
    local = local_root / rel if rel else local_root
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

    local_root, rel_inner = nas_mount_base_and_rel(user, rel_path)
    local_path = local_root / rel_inner if rel_inner else local_root

    if kind == 'file':
        try:
            if local_path.is_file():
                local_path.unlink()
                return name
        except OSError:
            pass
        delete_via_rclone(rel_path, user=user)
        return name

    if kind == 'dir':
        try:
            if local_path.is_dir():
                if any(local_path.iterdir()):
                    raise NasPathError('Chỉ xóa được thư mục rỗng.')
                local_path.rmdir()
                return name
        except NasPathError:
            raise
        except OSError:
            pass
        listing = list_directory_via_rclone(rel_path, user=user, fresh=True)
        if listing['folders'] or listing['files']:
            raise NasPathError('Chỉ xóa được thư mục rỗng.')
        delete_dir_via_rclone(rel_path, user=user)
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
