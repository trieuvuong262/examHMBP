"""Dump raw synoacl for a few shares to debug duplicate ACEs."""
from __future__ import annotations

import os
import sys

if __name__ == '__main__' and 'django' not in sys.modules:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
    import django
    django.setup()

from nas_storage.nas_acl_apply import _run_ssh_commands, parse_synoacl_get, _desired_synoacl_aces_for_permissions, _active_folder_permissions
from nas_storage.models import NasShareFolder
from nas_storage.permission_defs import detect_preset_from_flags


def main() -> None:
    for name in ('02_HANH_CHINH_NHAN_SU', '10_HE_THONG_CNTT', '00_QUY_DINH_CHUNG'):
        folder = NasShareFolder.objects.get(share_name=name, parent__isnull=True)
        print('\n====', name, '====')
        for perm in _active_folder_permissions(folder):
            print(' PORTAL', perm.assignee_label, detect_preset_from_flags(perm.permission_flags()), perm.resolved_nas_principal())
        aces = _desired_synoacl_aces_for_permissions(_active_folder_permissions(folder))
        print(' DESIRED', len(aces))
        for ace in aces:
            if ace.startswith('group:'):
                print('  ', ace)
        raw = _run_ssh_commands([f'/usr/syno/bin/synoacltool -get "{folder.resolved_volume_path()}"'])
        print(' RAW')
        for line in raw.splitlines():
            if '[' in line and 'level:' in line:
                print(' ', line.strip())
        rows = parse_synoacl_get(raw)
        print(' PARSED', len(rows))
        for r in rows:
            print(' ', r)


if __name__ == '__main__':
    main()
