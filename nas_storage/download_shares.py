"""Share NAS dùng cho bộ cài Windows (Thư viện → Tải NAS)."""

from __future__ import annotations

from django.contrib.auth.models import User

from nas_storage.dept_nas_config import (
    DEPT_NAS_SPECS,
    EXTRA_SHARE_GROUP_LINKS,
    is_portal_browse_hidden_share,
    nas_group_for_portal_department,
)
from nas_storage.models import NasUserFolderAccess
from nas_storage.nas_paths import normalize_rel_path, split_share_prefixed_path


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


def nas_mount_shares_for_user(user: User) -> list[str]:
    """Share ưu tiên: thư mục cấu hình riêng user → share mặc định phòng ban."""
    from hrm.models import Profile

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

    dept_name = (
        Profile.objects.filter(user_id=user.pk)
        .values_list('department__name', flat=True)
        .first()
    )
    group = nas_group_for_portal_department(dept_name)
    if group:
        for spec in DEPT_NAS_SPECS:
            if spec.nas_group == group and spec.share_name:
                add(spec.share_name)
        for share_name, link_group in EXTRA_SHARE_GROUP_LINKS:
            if link_group == group:
                add(share_name)

    return names
