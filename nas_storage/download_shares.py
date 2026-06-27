"""Share NAS dùng cho bộ cài Windows (NAS → Tải NAS)."""

from __future__ import annotations

from django.contrib.auth.models import User

from nas_storage.dept_nas_config import (
    DEPT_NAS_SPECS,
    EXTRA_SHARE_GROUP_LINKS,
    is_portal_browse_hidden_share,
    nas_group_for_portal_department,
)
from nas_storage.models import NasShareFolder, NasUserFolderAccess
from nas_storage.nas_paths import (
    department_default_nas_roots,
    normalize_rel_path,
    split_share_prefixed_path,
    user_department_folder_code,
    uses_dept_nas_root_remote,
)

# Tên dept/rclone (synology:KD-MKT) không phải shared folder DSM — map sang share WebDAV thật.
WEBDAV_SHARE_ALIASES: dict[str, str] = {
    'KD-MKT': '05_MARKETING',
}


def share_name_from_folder_rel(rel_path: str) -> str | None:
    """
    Suy ra tên shared folder Synology từ rel_path Portal.
    - ``10_HE_THONG_CNTT`` → share gốc
    - ``05_MARKETING/lvanhthu`` → ``05_MARKETING``
    - ``HCNS/user`` → None (đường dẫn trong share phòng ban, không phải tên share gốc)
    """
    rel = normalize_rel_path(rel_path)
    if not rel:
        return None
    if '/' in rel:
        share, _ = split_share_prefixed_path(rel)
        return share
    return rel


def resolve_webdav_share_name(name: str) -> str:
    """Chuẩn hóa tên share cho WebDAV Windows (synoshare thật trên DSM)."""
    n = (name or '').strip()
    if not n:
        return ''
    return WEBDAV_SHARE_ALIASES.get(n, n)


def webdav_share_from_rel_path(rel_path: str, *, user: User | None = None) -> str | None:
    """Suy ra share DSM mount WebDAV từ rel_path duyệt NAS trên Portal."""
    rel = normalize_rel_path(rel_path)
    if not rel:
        return None
    share, _inner = split_share_prefixed_path(rel)
    if share:
        return resolve_webdav_share_name(share)
    if user is not None:
        dept_code = user_department_folder_code(user)
        if dept_code and uses_dept_nas_root_remote(dept_code):
            return resolve_webdav_share_name(dept_code)
    return None


def portal_nas_rel_paths_for_user(user: User) -> list[str]:
    """Đường dẫn NAS user được duyệt trên Portal (custom / browse all / mặc định phòng ban)."""
    from nas_storage.portal_access import all_share_portal_roots, user_has_portal_browse_all
    from nas_storage.user_folders import custom_roots_from_db, user_has_custom_nas_folders

    paths: list[str] = []
    seen: set[str] = set()

    def add(rel: str) -> None:
        n = normalize_rel_path(rel)
        if not n or n in seen:
            return
        seen.add(n)
        paths.append(n)

    if user_has_custom_nas_folders(user):
        for entry in custom_roots_from_db(user):
            add(entry.rel_path)
    elif user_has_portal_browse_all(user):
        for entry in all_share_portal_roots():
            add(entry.rel_path)
    else:
        for entry in department_default_nas_roots(user):
            add(entry.rel_path)
        for rel in NasUserFolderAccess.objects.filter(user=user, is_active=True).order_by(
            'sort_order', 'id',
        ).values_list('rel_path', flat=True):
            add(rel)

    return paths


def nas_webdav_shares_from_portal_permissions(user: User) -> list[str]:
    """Share DSM từ phân quyền thư mục NAS (NasFolderPermission + nhóm Portal)."""
    from nas_storage.folder_permissions_resolved import effective_folder_permissions
    from nas_storage.permission_defs import has_read_access
    from nas_storage.portal_access import user_nas_access_groups

    group_ids = set(user_nas_access_groups(user).values_list('pk', flat=True))
    shares: list[str] = []
    seen: set[str] = set()

    for folder in NasShareFolder.objects.filter(is_active=True).order_by('sort_order', 'share_name', 'id'):
        if is_portal_browse_hidden_share(folder.share_name):
            continue
        matched = False
        for item in effective_folder_permissions(folder):
            perm = item.permission
            if perm.permission_type != 'allow':
                continue
            if not has_read_access(perm.permission_flags()):
                continue
            if perm.user_id == user.pk or (perm.group_id and perm.group_id in group_ids):
                matched = True
                break
        if not matched:
            continue
        resolved = resolve_webdav_share_name(folder.share_name)
        if not resolved or resolved in seen or is_portal_browse_hidden_share(resolved):
            continue
        seen.add(resolved)
        shares.append(resolved)

    return shares


def nas_mount_shares_for_user(user: User) -> list[str]:
    """Share legacy (nhóm NAS Portal + truy cập riêng) — fallback bổ sung cho phân quyền thư mục."""
    from nas_storage.portal_access import user_nas_access_groups

    names: list[str] = []
    seen: set[str] = set()

    def add(name: str | None) -> None:
        n = (name or '').strip()
        if not n or n in seen or is_portal_browse_hidden_share(n):
            return
        seen.add(n)
        names.append(n)

    for rel in NasUserFolderAccess.objects.filter(user=user, is_active=True).order_by(
        'sort_order', 'id',
    ).values_list('rel_path', flat=True):
        add(share_name_from_folder_rel(rel))

    group_names = set(user_nas_access_groups(user).values_list('name', flat=True))
    for spec in DEPT_NAS_SPECS:
        if spec.nas_group in group_names and spec.share_name:
            add(spec.share_name)
    for share_name, link_group in EXTRA_SHARE_GROUP_LINKS:
        if link_group in group_names:
            add(share_name)

    return names


def nas_webdav_shares_for_user(user: User) -> list[str]:
    """
    Share mount WebDAV — quét quyền Portal, dedupe, map alias rclone → synoshare DSM.
    """
    shares: list[str] = []
    seen: set[str] = set()

    def add_share(name: str | None) -> None:
        resolved = resolve_webdav_share_name(name or '')
        if not resolved or resolved in seen or is_portal_browse_hidden_share(resolved):
            return
        seen.add(resolved)
        shares.append(resolved)

    for name in nas_webdav_shares_from_portal_permissions(user):
        add_share(name)

    for rel in portal_nas_rel_paths_for_user(user):
        add_share(webdav_share_from_rel_path(rel, user=user))

    for raw in nas_mount_shares_for_user(user):
        add_share(raw)

    return shares
