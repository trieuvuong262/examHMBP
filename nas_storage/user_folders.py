"""Gán thư mục NAS theo user — tùy chỉnh thay cho map mặc định phòng ban."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.db import transaction

from nas_storage.models import NasUserFolderAccess
from nas_storage.nas_paths import NasRootEntry, department_default_nas_roots


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
