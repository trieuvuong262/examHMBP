"""Quyền duyệt thư mục NAS trên Portal theo nhóm NasAccessGroup."""

from __future__ import annotations

import os

from django.contrib.auth.models import User
from django.db.models import Q

from hrm.models import Profile
from nas_storage.dept_nas_config import (
    DEPARTMENT_NAS_GROUPS,
    is_portal_browse_hidden_share,
    nas_group_for_portal_department,
)
from nas_storage.nas_paths import NasRootEntry, nas_is_available, nas_mount_root


def _department_nas_group_name(user: User) -> str | None:
    dept_name = (
        Profile.objects.filter(user_id=user.pk)
        .values_list('department__name', flat=True)
        .first()
    )
    return nas_group_for_portal_department(dept_name)


def user_nas_access_groups(user: User):
    """Nhóm NAS áp dụng cho user: map phòng ban + thành viên bổ sung, trừ loại trừ."""
    from nas_storage.models import NasAccessGroup

    if not getattr(user, 'is_authenticated', False):
        return NasAccessGroup.objects.none()

    dept_group = _department_nas_group_name(user)
    qs = NasAccessGroup.objects.filter(is_active=True).exclude(portal_excluded_members=user)
    filters = Q(portal_members=user)
    if dept_group:
        filters |= Q(name=dept_group)
    return qs.filter(filters).distinct()


def _users_for_department_nas_group(group_name: str) -> list[User]:
    group_name = (group_name or '').strip()
    if not group_name:
        return []

    users: list[User] = []
    qs = (
        Profile.objects.filter(is_employed=True, user__is_active=True)
        .select_related('user', 'department')
        .order_by('full_name', 'user__username')
    )
    for profile in qs:
        dept_name = profile.department.name if profile.department_id else None
        if nas_group_for_portal_department(dept_name) == group_name:
            users.append(profile.user)
    return users


def users_auto_in_nas_group(
    group_name: str,
    *,
    excluded_user_ids: set[int] | None = None,
) -> list[User]:
    """User thuộc nhóm NAS qua map phòng ban, không nằm trong danh sách loại trừ."""
    excluded_user_ids = excluded_user_ids or set()
    return [u for u in _users_for_department_nas_group(group_name) if u.pk not in excluded_user_ids]


def users_excluded_from_nas_group(group_name: str, *, excluded_user_ids: set[int] | None = None) -> list[User]:
    """User thuộc phòng ban map sang nhóm nhưng bị loại trừ."""
    excluded_user_ids = excluded_user_ids or set()
    if not excluded_user_ids:
        return []
    return [u for u in _users_for_department_nas_group(group_name) if u.pk in excluded_user_ids]


def department_user_ids_for_nas_group(group_name: str) -> set[int]:
    return {u.pk for u in _users_for_department_nas_group(group_name)}


def user_has_portal_browse_all(user: User) -> bool:
    return user_nas_access_groups(user).filter(portal_browse_all=True).exists()


def all_share_portal_roots() -> list[NasRootEntry]:
    """Danh sách gốc duyệt NAS — share đã đăng ký + thư mục trên mount (nếu có)."""
    from nas_storage.models import NasShareFolder

    entries: list[NasRootEntry] = []
    seen: set[str] = set()

    for folder in NasShareFolder.objects.filter(is_active=True).order_by('sort_order', 'share_name'):
        if is_portal_browse_hidden_share(folder.share_name):
            continue
        seen.add(folder.share_name)
        entries.append(
            NasRootEntry(
                key=f'share_{folder.pk}',
                label=folder.display_name or folder.share_name,
                rel_path=folder.share_name,
                description=(folder.description or folder.share_name).strip(),
            ),
        )

    if nas_is_available():
        try:
            for name in sorted(os.listdir(nas_mount_root())):
                if name.startswith('.') or name in seen or is_portal_browse_hidden_share(name):
                    continue
                path = nas_mount_root() / name
                if not path.is_dir():
                    continue
                seen.add(name)
                entries.append(
                    NasRootEntry(
                        key=f'mount_{name}',
                        label=name,
                        rel_path=name,
                        description=name,
                    ),
                )
        except OSError:
            pass

    return entries


def sync_browse_all_share_permissions(*, apply_to_nas: bool = False) -> dict:
    """
  Tạo quyền đọc trên mọi share cho nhóm có portal_browse_all.
  Trả về thống kê permissions created/updated.
  """
    from nas_storage.models import NasAccessGroup, NasFolderPermission, NasShareFolder
    from nas_storage.nas_acl_apply import apply_folder_permissions
    from nas_storage.permission_defs import flags_from_preset

    stats = {'permissions_created': 0, 'permissions_updated': 0, 'folders_applied': 0}
    groups = NasAccessGroup.objects.filter(is_active=True, portal_browse_all=True)
    folders = [
        f for f in NasShareFolder.objects.filter(is_active=True)
        if not is_portal_browse_hidden_share(f.share_name)
    ]
    perm_defaults = {
        'permission_type': 'allow',
        'apply_to': 'all',
        'inherit_from_parent': False,
        **flags_from_preset('read'),
    }

    for group in groups:
        for folder in folders:
            perm, created = NasFolderPermission.objects.update_or_create(
                folder=folder,
                group=group,
                defaults=perm_defaults,
            )
            if created:
                stats['permissions_created'] += 1
            else:
                stats['permissions_updated'] += 1

    if apply_to_nas:
        for folder in folders:
            if folder.permissions.filter(group__portal_browse_all=True).exists():
                apply_folder_permissions(folder)
                stats['folders_applied'] += 1

    return stats
