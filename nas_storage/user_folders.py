"""Gán thư mục NAS theo user — tùy chỉnh thay cho map mặc định phòng ban."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db import connection, transaction

from nas_storage.models import NasUserFolderAccess
from nas_storage.nas_paths import NasRootEntry, department_default_nas_roots


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
    from nas_storage.nas_paths import department_default_nas_roots

    if not nas_folders_feature_available():
        return {
            'nas_migration_missing': True,
            'nas_formset': None,
            'nas_default_roots': [],
            'nas_using_custom': False,
        }

    if post_data is None:
        formset = build_nas_folder_formset(user=user)
    else:
        formset = build_nas_folder_formset(user=user, data=post_data)

    return {
        'nas_migration_missing': False,
        'nas_formset': formset,
        'nas_default_roots': department_default_nas_roots(user),
        'nas_using_custom': user_has_custom_nas_folders(user),
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


@transaction.atomic
def copy_department_defaults_to_user(user) -> int:
    """Tạo bản ghi tùy chỉnh từ map phòng ban hiện tại (tiện IT chỉnh sửa)."""
    if user_has_custom_nas_folders(user):
        return 0
    created = 0
    for idx, entry in enumerate(department_default_nas_roots(user)):
        NasUserFolderAccess.objects.create(
            user=user,
            label=entry.label,
            rel_path=entry.rel_path,
            description=entry.description,
            sort_order=idx,
            is_active=True,
        )
        created += 1
    return created
