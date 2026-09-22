"""Inspect folder 10 / perm 17 and all folder permission flags."""
from __future__ import annotations

import os
import sys

if __name__ == '__main__' and 'django' not in sys.modules:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
    import django
    django.setup()

from nas_storage.models import NasFolderPermission, NasShareFolder
from nas_storage.permission_defs import detect_preset_from_flags, ALL_PERM_FIELD_NAMES


def main() -> None:
    folder = NasShareFolder.objects.filter(pk=10).first()
    print('FOLDER', folder, folder.portal_path_label() if folder else None, folder.share_name if folder else None)
    perm = NasFolderPermission.objects.filter(pk=17).select_related('folder', 'group', 'user').first()
    print('PERM17', perm)
    if perm:
        flags = perm.permission_flags()
        print('  assignee', perm.assignee_label, perm.resolved_nas_principal())
        print('  preset', detect_preset_from_flags(flags))
        print('  flags', flags)

    print('\n=== ALL PERMISSIONS ===')
    counts: dict[str, int] = {}
    for p in NasFolderPermission.objects.select_related('folder', 'group', 'user').order_by('folder_id', 'id'):
        preset = detect_preset_from_flags(p.permission_flags())
        counts[preset] = counts.get(preset, 0) + 1
        print(
            f'pk={p.pk} folder={p.folder_id}:{p.folder.portal_path_label()} '
            f'root={p.folder.parent_id is None} target={p.assignee_label} preset={preset} '
            f'del={p.perm_delete} del_child={p.perm_delete_children} write={p.perm_create_files}'
        )
    print('\nCOUNTS', counts)
    print('FOLDERS', list(NasShareFolder.objects.values_list('pk', 'share_name', 'sub_path', 'parent_id')))


if __name__ == '__main__':
    main()
