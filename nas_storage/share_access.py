"""Truy cập NAS qua liên kết chia sẻ — chỉ user Portal đã đăng nhập."""

from __future__ import annotations

from pathlib import Path

from django.utils import timezone

from nas_storage.models import NasShareLink
from nas_storage.nas_paths import NasPathError, normalize_rel_path, nas_mount_root


def is_path_under_share(rel_path: str, share_root: str) -> bool:
    rel = normalize_rel_path(rel_path)
    root = normalize_rel_path(share_root)
    if not root:
        return False
    return rel == root or rel.startswith(root + '/')


def resolve_mount_path(rel_path: str) -> Path:
    rel = normalize_rel_path(rel_path)
    if not rel:
        raise NasPathError('Chưa chọn thư mục.')

    mount = nas_mount_root()
    candidate = (mount / rel).resolve()
    mount_resolved = mount.resolve()
    try:
        candidate.relative_to(mount_resolved)
    except ValueError as exc:
        raise NasPathError('Đường dẫn ngoài phạm vi NAS.') from exc
    return candidate


def get_share_token_from_request(request) -> str:
    return (request.GET.get('share') or request.POST.get('share') or '').strip()


def get_active_share(token: str | None) -> NasShareLink | None:
    if not token:
        return None
    try:
        share = NasShareLink.objects.select_related('created_by').get(token=token, is_active=True)
    except (NasShareLink.DoesNotExist, ValueError):
        return None
    if share.is_expired():
        share.deactivate_if_expired()
        return None
    return share


def resolve_path_for_request(user, rel_path: str, share: NasShareLink | None = None) -> Path:
    """Đường dẫn NAS — quyền thường hoặc qua liên kết chia sẻ."""
    from nas_storage.nas_paths import resolve_nas_path

    if share:
        if not is_path_under_share(rel_path, share.rel_path):
            raise NasPathError('Liên kết chia sẻ không áp dụng cho mục này.')
        return resolve_mount_path(rel_path)
    return resolve_nas_path(user, rel_path)


def get_or_create_share(user, rel_path: str, *, item_name: str, is_dir: bool) -> NasShareLink:
    rel = normalize_rel_path(rel_path)
    now = timezone.now()
    existing = NasShareLink.objects.filter(
        created_by=user,
        rel_path=rel,
        is_active=True,
        expires_at__gt=now,
    ).first()
    if existing:
        return existing

    return NasShareLink.objects.create(
        created_by=user,
        rel_path=rel,
        item_name=item_name,
        is_dir=is_dir,
        expires_at=NasShareLink.default_expiry(),
    )
