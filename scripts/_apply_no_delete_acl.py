"""Convert RW→no-delete, apply ACL folder 10, verify masks."""
from __future__ import annotations

import os
import sys

if __name__ == '__main__' and 'django' not in sys.modules:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
    import django
    django.setup()

from nas_storage.models import NasFolderPermission, NasShareFolder
from nas_storage.nas_acl_apply import apply_folder_permissions, parse_synoacl_get, _run_ssh_commands
from nas_storage.permission_defs import (
    convert_read_write_permissions_to_no_delete,
    detect_preset_from_flags,
)


NO_DEL = 'rwxp--aARWc--'
FULL_DEL = 'rwxpdDaARWcCo'
RW_DEL = 'rwxpdDaARWc--'


def acl_of(path: str) -> list[dict]:
    out = _run_ssh_commands([f'/usr/syno/bin/synoacltool -get "{path}"'])
    return parse_synoacl_get(out)


def main() -> None:
    before = {}
    for perm in NasFolderPermission.objects.iterator():
        p = detect_preset_from_flags(perm.permission_flags())
        before[p] = before.get(p, 0) + 1
    print('BEFORE', before)
    updated = convert_read_write_permissions_to_no_delete()
    print('converted', updated)
    after = {}
    for perm in NasFolderPermission.objects.iterator():
        p = detect_preset_from_flags(perm.permission_flags())
        after[p] = after.get(p, 0) + 1
    print('AFTER', after)

    folder = NasShareFolder.objects.get(pk=10)
    print('APPLY', folder.portal_path_label())
    result = apply_folder_permissions(folder)
    print('apply_status', result.get('status'), 'acl_changed', result.get('acl_changed'), 'share_added', result.get('added'))
    rows = acl_of(folder.resolved_volume_path())
    print('ACE_COUNT', len(rows))
    for row in rows:
        if row['level'] != 0:
            continue
        name = row['name']
        perm = row['perm']
        interesting = name.lower() in {
            'administrators', 'tgd@ldap.justplay.local', 'mkt@ldap.justplay.local',
            'tckt@ldap.justplay.local', 'ductn@ldap.justplay.local',
        } or name.lower().startswith('tgd') or name.lower().startswith('mkt') or name.lower().startswith('tckt')
        if interesting or ('d' in perm[4:6] and name):
            flag = 'HAS_DEL' if 'd' in perm[4:6].lower() or perm[4:6] != '--' else 'NO_DEL'
            # perm indices 4=d 5=D
            d_bit = perm[4] if len(perm) > 5 else '?'
            D_bit = perm[5] if len(perm) > 5 else '?'
            print(f'  {row["kind"]}:{name} perm={perm} d={d_bit} D={D_bit}')

    tgd = next((r for r in rows if r['name'].lower().startswith('tgd@')), None)
    mkt = next((r for r in rows if r['name'].lower().startswith('mkt@')), None)
    tckt = next((r for r in rows if r['name'].lower().startswith('tckt@')), None)
    print('CHECK TGD', tgd['perm'] if tgd else None, 'expect d/D set')
    print('CHECK MKT', mkt['perm'] if mkt else None, 'expect no d/D')
    print('CHECK TCKT', tckt['perm'] if tckt else None, 'expect no d/D')
    if tgd and tgd['perm'][4] == '-' and tgd['perm'][5] == '-':
        raise SystemExit('FAIL TGD lost delete')
    if mkt and (mkt['perm'][4] != '-' or mkt['perm'][5] != '-'):
        raise SystemExit('FAIL MKT still can delete')
    if tckt and (tckt['perm'][4] != '-' or tckt['perm'][5] != '-'):
        raise SystemExit('FAIL TCKT still can delete')
    print('FOLDER10 ACL OK')


if __name__ == '__main__':
    main()
