"""Gán thư mục NAS theo user — chỉ dùng danh sách cấu hình thủ công."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db import connection

from nas_storage.models import NasUserFolderAccess
from nas_storage.nas_paths import NasRootEntry, normalize_rel_path


def portal_rel_path_for_acl(*, share_name: str, sub_path: str) -> str:
    share = (share_name or '').strip().strip('/')
    sub = (sub_path or '').strip().strip('/')
    if not share:
        return ''
    return normalize_rel_path(f'{share}/{sub}' if sub else share)


def ensure_portal_link_for_acl(grant) -> tuple[NasUserFolderAccess, bool]:
    """
    Tạo/cập nhật link Duyệt thư mục Portal khớp ACL truy cập riêng (share/sub_path).
    Trả về (bản ghi, created).
    """
    from nas_storage.models import NasUserFolderAcl

    if not isinstance(grant, NasUserFolderAcl) or not grant.is_active:
        raise ValueError('grant không hợp lệ')
    rel_path = portal_rel_path_for_acl(
        share_name=grant.folder.share_name,
        sub_path=grant.sub_path,
    )
    if not rel_path:
        raise ValueError('Thiếu share/thư mục con')
    label = (grant.label or '').strip() or f'/{rel_path}'
    return NasUserFolderAccess.objects.update_or_create(
        user=grant.user,
        rel_path=rel_path,
        defaults={
            'label': label[:120],
            'description': rel_path,
            'is_active': True,
        },
    )


def nas_folders_feature_available() -> bool:
    """False khi migration 0003 chưa chạy trên DB."""
    try:
        return NasUserFolderAccess._meta.db_table in connection.introspection.table_names()
    except Exception:
        return False


def user_has_custom_nas_folders(user) -> bool:
    return NasUserFolderAccess.objects.filter(user=user, is_active=True).exists()


def get_user_nas_folder_queryset(user):
    return NasUserFolderAccess.objects.filter(user=user).order_by('sort_order', 'id')


def custom_roots_from_db(user) -> list[NasRootEntry]:
    entries = []
    for row in NasUserFolderAccess.objects.filter(user=user, is_active=True).order_by(
        'sort_order', 'id',
    ):
        entries.append(
            NasRootEntry(
                key=f'custom_{row.pk}',
                label=row.label,
                rel_path=row.rel_path,
                description=(row.description or row.rel_path).strip(),
            ),
        )
    return entries


def save_user_nas_folder_formset(user, formset) -> None:
    """Lưu formset sau khi user_edit hợp lệ."""
    instances = formset.save(commit=False)
    for obj in instances:
        obj.user = user
        obj.save()
    for obj in formset.deleted_objects:
        obj.delete()


def nas_folders_page_context(user: User, *, post_data=None) -> dict:
    """Context cho trang / dashboard/users/<id>/nas-folders/."""
    if not nas_folders_feature_available():
        return {
            'nas_migration_missing': True,
            'nas_formset': None,
            'nas_using_custom': False,
            'nas_active_count': 0,
        }

    if post_data is None:
        formset = build_nas_folder_formset(user=user)
    else:
        formset = build_nas_folder_formset(user=user, data=post_data)

    active_count = NasUserFolderAccess.objects.filter(user=user, is_active=True).count()
    return {
        'nas_migration_missing': False,
        'nas_formset': formset,
        'nas_using_custom': active_count > 0,
        'nas_active_count': active_count,
    }


def build_nas_folder_formset(*, user: User, data=None):
    from nas_storage.forms import NasUserFolderAccessFormSet

    queryset = get_user_nas_folder_queryset(user)
    if data is None:
        return NasUserFolderAccessFormSet(
            queryset=queryset,
            prefix='nas_folders',
        )
    return NasUserFolderAccessFormSet(
        data,
        queryset=queryset,
        prefix='nas_folders',
    )
