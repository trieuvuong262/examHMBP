"""Check Portal UI preset + folder 10 / perm 17 after no-delete conversion."""
from __future__ import annotations

import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
import django
django.setup()

from nas_storage.forms import NasFolderPermissionForm
from nas_storage.models import NasFolderPermission, NasShareFolder
from nas_storage.permission_defs import PRESET_FORM_CHOICES, detect_preset_from_flags


def main() -> None:
    print('CHOICES', list(PRESET_FORM_CHOICES))
    folder = NasShareFolder.objects.filter(pk=10).first() or NasShareFolder.objects.filter(
        share_name='04_KINH_DOANH_CSKH', parent__isnull=True
    ).first()
    print('FOLDER', folder.pk if folder else None, folder.share_name if folder else None, folder.display_name if folder else None)
    perm = NasFolderPermission.objects.filter(pk=17).select_related('group', 'user', 'folder').first()
    if perm:
        print(
            'PERM17',
            perm.folder.share_name,
            perm.assignee_label,
            detect_preset_from_flags(perm.permission_flags()),
            perm.access_level_label,
        )
        form = NasFolderPermissionForm(instance=perm, folder=perm.folder)
        print('EDIT_INITIAL', form.fields['preset'].initial)
    new_form = NasFolderPermissionForm(folder=folder)
    print('NEW_INITIAL', new_form.fields['preset'].initial)

    by_folder = {}
    for p in NasFolderPermission.objects.select_related('folder', 'group').iterator():
        preset = detect_preset_from_flags(p.permission_flags())
        by_folder.setdefault(p.folder_id, []).append(preset)
    print('FOLDERS_WITH_PERMS', len(by_folder))
    print('NEW_FORM_CHOICES', [c[0] for c in new_form.fields['preset'].choices])


if __name__ == '__main__':
    main()
