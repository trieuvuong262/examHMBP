"""Cây thư mục NAS của hồ sơ thiết kế.

Thiết Kế Sản Phẩm / {tên sản phẩm} ({mã}) / Tổng Quan | Thiết Kế | Kỹ Thuật | May Mẫu | Trao Đổi | Giá Thành
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import uuid
from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.utils.text import get_valid_filename

from san_xuat.design_nas_storage import design_nas_rel_base

logger = logging.getLogger(__name__)
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_OBJECT_COUNT = re.compile(r'Total objects:\s+(\d+)')

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
NAS_ROOT = 'Thiết Kế Sản Phẩm'
LEGACY_NAS_ROOTS = frozenset({'thiet_ke_sp', NAS_ROOT})


def safe_segment(value: str, fallback: str) -> str:
    text = _ILLEGAL.sub('', (value or '').replace('\u00a0', ' ')).strip()
    text = re.sub(r'\s+', ' ', text).rstrip('. ')
    return (text or fallback)[:80]


def folder_name_for(name: str, code: str) -> str:
    return f'{safe_segment(name, "ho-so")} ({safe_segment(code, "ma")})'


def dossier_folder_name(dossier) -> str:
    return folder_name_for(dossier.name, dossier.code)


def dossier_prefix(dossier) -> str:
    return f'{NAS_ROOT}/{dossier_folder_name(dossier)}'


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


def _rclone(verb: str, *rels: str) -> subprocess.CompletedProcess:
    from nas_storage.nas_paths import _rclone_env, app_storage_rclone_target

    args = ['rclone', verb]
    args.extend(app_storage_rclone_target(design_nas_rel_base(), rel) for rel in rels)
    args.extend(['--contimeout', '15s', '--timeout', '90s', '--retries', '2'])
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=100,
        check=False,
        env=_rclone_env(),
    )


def _rclone_text(proc: subprocess.CompletedProcess) -> str:
    return ((proc.stderr or '') + '\n' + (proc.stdout or '')).strip()


def _require_rclone(proc: subprocess.CompletedProcess) -> None:
    if proc.returncode != 0:
        raise OSError(_rclone_text(proc)[:300] or 'rclone failed')


def _tree_state(rel: str) -> str:
    """missing | empty | files. Không stat mount FUSE — mount lỗi sẽ treo request."""
    proc = _rclone('size', rel)
    if proc.returncode != 0:
        return 'missing'
    match = _OBJECT_COUNT.search(proc.stdout or '')
    count = int(match.group(1)) if match else 0
    return 'files' if count else 'empty'


def _take_folder(old_rel: str, new_rel: str) -> None:
    """Đổi tên cả thư mục hồ sơ. Thư mục đích đã tồn tại thì gộp file rồi xóa thư mục cũ."""
    if old_rel == new_rel:
        return
    old_state = _tree_state(old_rel)
    if old_state == 'missing':
        return
    new_state = _tree_state(new_rel)
    if new_state == 'missing':
        _require_rclone(_rclone('moveto', old_rel, new_rel))
        return
    if new_state == 'empty':
        _require_rclone(_rclone('purge', new_rel))
        _require_rclone(_rclone('moveto', old_rel, new_rel))
        return
    if old_state == 'files':
        _require_rclone(_rclone('move', old_rel, new_rel))
    _require_rclone(_rclone('purge', old_rel))


def _rewrite_folder_prefix(dossier, old_folder: str, new_folder: str) -> int:
    updated = 0
    new_prefix = f'{NAS_ROOT}/{new_folder}/'
    for root in LEGACY_NAS_ROOTS:
        old_prefix = f'{root}/{old_folder}/'
        rows = dossier.attachments.filter(file__startswith=old_prefix)
        for att in rows.iterator():
            name = (att.file.name or '').replace('\\', '/')
            if not name.startswith(old_prefix):
                continue
            dossier.attachments.filter(pk=att.pk).update(file=new_prefix + name[len(old_prefix):])
            updated += 1
    return updated


def relocate_dossier_files(dossier, previous_name: str | None = None) -> int:
    """Đổi tên thư mục NAS theo tên sản phẩm, rồi xóa thư mục tên cũ."""
    current = dossier_folder_name(dossier)
    folders: set[str] = set()
    if previous_name and previous_name != dossier.name:
        folders.add(folder_name_for(previous_name, dossier.code))
    for name in dossier.attachments.exclude(file='').values_list('file', flat=True):
        parts = (name or '').replace('\\', '/').lstrip('/').split('/')
        if len(parts) >= 2 and parts[0] in LEGACY_NAS_ROOTS and parts[1] and parts[1] != current:
            folders.add(parts[1])
    folders.discard(current)
    moved = 0
    for old_folder in folders:
        new_rel = f'{NAS_ROOT}/{current}'
        for root in LEGACY_NAS_ROOTS:
            _take_folder(f'{root}/{old_folder}', new_rel)
        moved += _rewrite_folder_prefix(dossier, old_folder, current)
    try:
        ensure_dossier_folders(dossier)
    except OSError:
        logger.exception('Không tạo đủ thư mục tab cho hồ sơ %s', dossier.pk)
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
                    relocate_dossier_files(dossier, previous_name=prev)
            except OSError:
                logger.exception('Không đổi được thư mục NAS của hồ sơ %s', pk)
                if not created and prev != name:
                    raise

        transaction.on_commit(run)

    pre_save.connect(stash_name, sender=ProductDevelopment, dispatch_uid='tksp_nas_stash_name')
    post_save.connect(sync_folders, sender=ProductDevelopment, dispatch_uid='tksp_nas_sync_folders')
