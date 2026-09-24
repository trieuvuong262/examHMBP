"""Restore delete bits so SMB move/rename works; re-apply ACL."""
from __future__ import annotations

import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
import django
django.setup()

from nas_storage.models import NasFolderPermission, NasShareFolder
from nas_storage.nas_acl_apply import apply_folder_permissions, parse_synoacl_get, _run_ssh_commands
from nas_storage.nas_acl_jobs import nas_acl_job_running, spawn_nas_acl_batch_job
from nas_storage.permission_defs import (
    convert_no_delete_permissions_to_read_write,
    detect_preset_from_flags,
)

SAMPLE = (
    '04_KINH_DOANH_CSKH',
    '02_HANH_CHINH_NHAN_SU',
    '07_SAN_XUAT',
    '10_HE_THONG_CNTT',
)


def acl_groups(path: str) -> list[dict]:
    out = _run_ssh_commands([f'/usr/syno/bin/synoacltool -get "{path}"'])
    return [
        r for r in parse_synoacl_get(out)
        if r['level'] == 0 and r['action'] == 'allow' and r['kind'] == 'group' and r['name']
    ]


def main() -> None:
    updated = convert_no_delete_permissions_to_read_write()
    counts: dict[str, int] = {}
    for perm in NasFolderPermission.objects.iterator():
        preset = detect_preset_from_flags(perm.permission_flags())
        counts[preset] = counts.get(preset, 0) + 1
    print('CONVERTED', updated)
    print('PRESETS', counts)

    probe = NasShareFolder.objects.filter(share_name='04_KINH_DOANH_CSKH', parent__isnull=True).first()
    if not probe:
        raise SystemExit('missing 04_KINH_DOANH_CSKH')
    result = apply_folder_permissions(probe)
    print('PROBE', result.get('status'), 'acl_changed=', result.get('acl_changed'))
    groups = acl_groups(probe.resolved_volume_path())
    mkt = next((g for g in groups if g['name'].lower().startswith('mkt@')), None)
    tgd = next((g for g in groups if g['name'].lower().startswith('tgd@')), None)
    print('MKT', mkt['perm'] if mkt else None)
    print('TGD', tgd['perm'] if tgd else None)
    if not mkt or mkt['perm'][4:6] == '--':
        raise SystemExit('PROBE_FAIL MKT still no-delete')
    if not tgd or 'd' not in tgd['perm'][4:6]:
        raise SystemExit('PROBE_FAIL TGD missing delete')
    print('PROBE_OK')

    roots = list(
        NasShareFolder.objects.filter(is_active=True, parent__isnull=True).order_by('sort_order', 'share_name')
    )
    errors = []
    for folder in roots:
        try:
            result = apply_folder_permissions(folder)
            print(f'{folder.share_name}: {result.get("status")} acl_changed={result.get("acl_changed")}')
        except Exception as exc:
            errors.append(f'{folder.share_name}: {exc}')
            print('ERR', folder.share_name, exc)

    print('\n=== SAMPLE ===')
    for name in SAMPLE:
        folder = NasShareFolder.objects.filter(share_name=name, parent__isnull=True).first()
        if not folder:
            continue
        print(f'\n{name}')
        for row in acl_groups(folder.resolved_volume_path()):
            dD = row['perm'][4:6] if len(row['perm']) >= 6 else '??'
            print(f'  {row["name"]} {row["perm"]} dD={dD}')

    if errors:
        print('ROOT_ERRORS', errors)
        raise SystemExit(1)

    spawned = False
    if not nas_acl_job_running('apply_nas_acl_all'):
        spawned = spawn_nas_acl_batch_job('apply_nas_acl_all')
    print('SPAWN_ALL', spawned)
    print('ROOTS_OK')


if __name__ == '__main__':
    main()
