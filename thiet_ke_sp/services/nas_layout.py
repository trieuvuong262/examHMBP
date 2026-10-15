"""Cây thư mục NAS của hồ sơ thiết kế.

thiet_ke_sp / {tên sản phẩm} ({mã}) / Tổng Quan | Thiết Kế | Kỹ Thuật | May Mẫu | Trao Đổi | Giá Thành
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import uuid
from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.utils.text import get_valid_filename

from san_xuat.design_nas_storage import (
    design_nas_abs_root,
    design_nas_rel_base,
    pending_exists,
    pending_path,
)

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

TAB_FOLDERS = {
    'overview': 'Tổng Quan',
    'design': 'Thiết Kế',
    'technical': 'Kỹ Thuật',
    'sample': 'May Mẫu',
    'files': 'Trao Đổi',
    'costing': 'Giá Thành',
}
KIND_FOLDERS = {
    'product_photo': 'Tổng Quan',
    'reference': 'Tổng Quan',
    'front': 'Thiết Kế',
    'back': 'Thiết Kế',
    'detail': 'Thiết Kế',
    'design_source': 'Thiết Kế',
    'design_preview': 'Thiết Kế',
    'colorway': 'Thiết Kế',
    'pattern': 'Kỹ Thuật',
    'tech_spec': 'Kỹ Thuật',
    'sample_photo': 'May Mẫu',
    'evaluation': 'May Mẫu',
    'cost': 'Giá Thành',
    'other': 'Trao Đổi',
}
ALL_FOLDERS = (
    'Tổng Quan', 'Thiết Kế', 'Kỹ Thuật', 'May Mẫu', 'Trao Đổi', 'Giá Thành',
)


def safe_segment(value: str, fallback: str) -> str:
    text = _ILLEGAL.sub('', (value or '').replace('\u00a0', ' ')).strip()
    text = re.sub(r'\s+', ' ', text).rstrip('. ')
    return (text or fallback)[:80]


def dossier_folder_name(dossier) -> str:
    return f'{safe_segment(dossier.name, "ho-so")} ({safe_segment(dossier.code, "ma")})'


def dossier_prefix(dossier) -> str:
    return f'thiet_ke_sp/{dossier_folder_name(dossier)}'


def folder_for_tab(tab: str) -> str:
    return TAB_FOLDERS.get(tab or '', '')


def folder_for_kind(kind: str) -> str:
    return KIND_FOLDERS.get(kind or '', 'Trao Đổi')


def upload_relpath(instance, filename: str) -> str:
    dossier = instance.dossier
    folder = getattr(instance, 'nas_folder', None) or folder_for_kind(instance.kind)
    safe = get_valid_filename(os.path.basename(filename or '')) or 'file'
    stem = uuid.uuid4().hex[:12]
    return f'{dossier_prefix(dossier)}/{folder}/{stem}_{safe}'


def _design_rel(folder_under_design: str) -> str:
    return f'{design_nas_rel_base()}/{folder_under_design}'.strip('/')


def ensure_dossier_folders(dossier) -> None:
    from nas_storage.app_nas_storage import persist_app_nas_mkdir

    prefix = dossier_prefix(dossier)
    for folder in ALL_FOLDERS:
        persist_app_nas_mkdir(_design_rel(f'{prefix}/{folder}'))


def _target_rel(dossier, att) -> str | None:
    old = (att.file.name or '').replace('\\', '/').lstrip('/')
    parts = old.split('/')
    if len(parts) < 3 or parts[0] != 'thiet_ke_sp' or not parts[-1]:
        return None
    current = dossier_folder_name(dossier)
    if len(parts) >= 4 and parts[2] in ALL_FOLDERS:
        if parts[1] == current:
            return None
        parts[1] = current
        return '/'.join(parts)
    if len(parts) == 3:
        return f'thiet_ke_sp/{current}/{folder_for_kind(att.kind)}/{parts[2]}'
    return None


def _move_stored(old_rel: str, new_rel: str) -> bool:
    if old_rel == new_rel:
        return True
    if pending_exists(old_rel):
        dest = pending_path(new_rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(pending_path(old_rel)), str(dest))
        return True
    from nas_storage.nas_mount_health import mount_io_safe

    src = design_nas_abs_root() / old_rel
    dest = design_nas_abs_root() / new_rel
    if mount_io_safe(src.parent):
        try:
            if src.is_file():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dest))
                return True
        except OSError:
            pass
    from nas_storage.app_nas_storage import persist_app_nas_mkdir
    from nas_storage.nas_paths import _rclone_env, app_storage_rclone_target

    persist_app_nas_mkdir(_design_rel(new_rel.rsplit('/', 1)[0]))
    proc = subprocess.run(
        [
            'rclone', 'moveto',
            app_storage_rclone_target(design_nas_rel_base(), old_rel),
            app_storage_rclone_target(design_nas_rel_base(), new_rel),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=_rclone_env(),
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or '').strip()
        raise OSError(err[:200] or 'move failed')
    return True


def relocate_dossier_files(dossier) -> int:
    """Đưa file cũ vào cây thư mục theo tab, và đổi tên thư mục khi tên sản phẩm đổi."""
    ensure_dossier_folders(dossier)
    attachments = list(dossier.attachments.exclude(file=''))
    planned: dict[str, str] = {}
    for att in attachments:
        old = (att.file.name or '').replace('\\', '/').lstrip('/')
        new = _target_rel(dossier, att)
        if new and new != old:
            planned.setdefault(old, new)
    moved = 0
    for old, new in planned.items():
        _move_stored(old, new)
        moved += dossier.attachments.filter(file=old).update(file=new)
    return moved


def connect_signals() -> None:
    from thiet_ke_sp.models import ProductDevelopment

    def stash_name(sender, instance, **kwargs):
        if not instance.pk:
            instance._nas_prev_name = None
            return
        instance._nas_prev_name = (
            sender.objects.filter(pk=instance.pk).values_list('name', flat=True).first()
        )

    def sync_folders(sender, instance, created, **kwargs):
        prev = getattr(instance, '_nas_prev_name', None)
        name = instance.name
        pk = instance.pk

        def run():
            dossier = sender.objects.filter(pk=pk).first()
            if dossier is None:
                return
            try:
                if created:
                    ensure_dossier_folders(dossier)
                elif prev != name:
                    relocate_dossier_files(dossier)
            except OSError:
                return

        transaction.on_commit(run)

    pre_save.connect(stash_name, sender=ProductDevelopment, dispatch_uid='tksp_nas_stash_name')
    post_save.connect(sync_folders, sender=ProductDevelopment, dispatch_uid='tksp_nas_sync_folders')
