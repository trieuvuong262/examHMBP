"""Thư mục NAS gán riêng theo user (NasUserFolderAcl) — ẩn khỏi user khác trên Portal."""

from __future__ import annotations

from django.contrib.auth.models import User

from nas_storage.nas_paths import NasPathError, normalize_rel_path
from nas_storage.user_folders import portal_rel_path_for_acl


def private_folder_owner_map() -> dict[str, int]:
    """Map đường dẫn Portal (chuẩn hóa, chữ thường) → user_id sở hữu thư mục riêng."""
    from nas_storage.models import NasUserFolderAcl

    owners: dict[str, int] = {}
    for grant in NasUserFolderAcl.objects.filter(is_active=True).select_related('folder', 'user'):
        rel = portal_rel_path_for_acl(
            share_name=grant.folder.share_name,
            sub_path=grant.sub_path,
        )
        if rel:
            owners[rel.lower()] = grant.user_id
    return owners


def private_folder_owner_id(rel_path: str) -> int | None:
    rel = normalize_rel_path(rel_path).lower()
    if not rel:
        return None
    owners = private_folder_owner_map()
    if rel in owners:
        return owners[rel]
    for private_rel, owner_id in owners.items():
        if rel.startswith(private_rel + '/'):
            return owner_id
    return None


def _child_rel_path(parent_rel: str, name: str) -> str:
    parent = normalize_rel_path(parent_rel)
    name = (name or '').strip()
    if not name:
        return parent
    return normalize_rel_path(f'{parent}/{name}' if parent else name)


def user_can_access_private_nas_rel(user: User | None, rel_path: str) -> bool:
    owner_id = private_folder_owner_id(rel_path)
    if owner_id is None:
        return True
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    return user.pk == owner_id


def filter_listing_folders_for_user(user: User | None, parent_rel: str, folders: list[dict]) -> list[dict]:
    """Ẩn thư mục con gán riêng cho user khác khi duyệt share cha."""
    visible: list[dict] = []
    for item in folders:
        name = (item.get('name') or '').strip()
        if not name:
            continue
        try:
            child_rel = _child_rel_path(parent_rel, name)
        except NasPathError:
            continue
        if user_can_access_private_nas_rel(user, child_rel):
            visible.append(item)
    return visible
