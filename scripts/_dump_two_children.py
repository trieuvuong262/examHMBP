"""Dump synoacl of two child folders that lacked level-0 TGD."""
from __future__ import annotations

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from nas_storage.models import NasShareFolder
from nas_storage.nas_acl_apply import _active_folder_permissions, _run_ssh_commands
from nas_storage.permission_defs import detect_preset_from_flags

NAMES = (
    '4.Gia_tri_cot_loi_Tam_nhin_Su_menh',
    '5.Quy_che_luong_thuong',
)

for folder in NasShareFolder.objects.filter(sub_path__icontains='Gia_tri_cot_loi') | NasShareFolder.objects.filter(sub_path__icontains='Quy_che_luong'):
    print('====', folder.pk, folder.portal_path_label(), folder.resolved_volume_path())
    for perm in _active_folder_permissions(folder):
        print(' LOCAL', perm.assignee_label, detect_preset_from_flags(perm.permission_flags()), 'inherit', perm.inherit_from_parent)
    print(_run_ssh_commands([f'/usr/syno/bin/synoacltool -get "{folder.resolved_volume_path()}"']))
