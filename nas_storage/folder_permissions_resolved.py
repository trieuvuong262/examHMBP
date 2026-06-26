"""Kế thừa phân quyền thư mục NAS (gốc → con)."""

from __future__ import annotations

from dataclasses import dataclass

from nas_storage.models import NasFolderPermission, NasShareFolder


@dataclass(frozen=True)
class EffectiveFolderPermission:
    permission: NasFolderPermission
    source: str  # 'local' | 'inherited'
    source_folder: NasShareFolder


def _assignee_key(perm: NasFolderPermission) -> tuple[str, int] | None:
    if perm.user_id:
        return ('user', perm.user_id)
    if perm.group_id:
        return ('group', perm.group_id)
    return None


def effective_folder_permissions(
    folder: NasShareFolder,
) -> list[EffectiveFolderPermission]:
    """Quyền hiệu lực: local ghi đè, còn lại kế thừa từ cha nếu bật inherits_permissions."""
    local_by_key: dict[tuple[str, int], NasFolderPermission] = {}
    for perm in folder.permissions.select_related('group', 'user').order_by('id'):
        key = _assignee_key(perm)
        if key:
            local_by_key[key] = perm

    merged: dict[tuple[str, int], EffectiveFolderPermission] = {
        key: EffectiveFolderPermission(permission=perm, source='local', source_folder=folder)
        for key, perm in local_by_key.items()
    }

    if folder.inherits_permissions and folder.parent_id:
        for item in effective_folder_permissions(folder.parent):
            key = _assignee_key(item.permission)
            if key and key not in merged:
                merged[key] = EffectiveFolderPermission(
                    permission=item.permission,
                    source='inherited',
                    source_folder=item.source_folder,
                )

    return sorted(
        merged.values(),
        key=lambda x: (
            0 if x.source == 'local' else 1,
            x.permission.group.sort_order if x.permission.group_id else 999,
            x.permission.user.username if x.permission.user_id else '',
            x.permission.id,
        ),
    )


def local_folder_permissions(folder: NasShareFolder):
    return folder.permissions.select_related('group', 'user', 'user__profile').order_by(
        'group__sort_order',
        'user__username',
        'id',
    )
