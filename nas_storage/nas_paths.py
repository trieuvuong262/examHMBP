"""Đường dẫn NAS an toàn — map phòng ban + account Portal."""

from __future__ import annotations

import mimetypes
import os
from dataclasses import dataclass
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


def list_directory(path: Path) -> dict:
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
