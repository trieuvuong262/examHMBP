"""Quyền duyệt thư mục NAS trên Portal theo nhóm NasAccessGroup."""

from __future__ import annotations

import os

from django.contrib.auth.models import User
from django.db.models import Q

from hrm.models import Profile
from nas_storage.dept_nas_config import nas_group_for_portal_department
from nas_storage.nas_paths import NasRootEntry, nas_is_available, nas_mount_root


def _department_nas_group_name(user: User) -> str | None:
    dept_name = (
        Profile.objects.filter(user_id=user.pk)
        .values_list('department__name', flat=True)
        .first()
    )
    return nas_group_for_portal_department(dept_name)


def user_nas_access_groups(user: User):
    """Nhóm NAS áp dụng cho user: map phòng ban + thành viên bổ sung."""
    from nas_storage.models import NasAccessGroup

    if not getattr(user, 'is_authenticated', False):
        return NasAccessGroup.objects.none()

    dept_group = _department_nas_group_name(user)
    filters = Q(portal_members=user)
    if dept_group:
        filters |= Q(name=dept_group)
    return NasAccessGroup.objects.filter(filters, is_active=True).distinct()


def user_has_portal_browse_all(user: User) -> bool:
    return user_nas_access_groups(user).filter(portal_browse_all=True).exists()


def all_share_portal_roots() -> list[NasRootEntry]:
    """Danh sách gốc duyệt NAS — share đã đăng ký + thư mục trên mount (nếu có)."""
    from nas_storage.models import NasShareFolder

    entries: list[NasRootEntry] = []
    seen: set[str] = set()

    for folder in NasShareFolder.objects.filter(is_active=True).order_by('sort_order', 'share_name'):
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
                if name.startswith('.') or name in seen:
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
    folders = list(NasShareFolder.objects.filter(is_active=True))
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
