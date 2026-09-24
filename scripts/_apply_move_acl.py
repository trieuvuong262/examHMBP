"""Apply move-capable no-delete ACL (delete bits on, recycle bin)."""
from __future__ import annotations

import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
import django
django.setup()

from nas_storage.models import NasFolderPermission, NasShareFolder
from nas_storage.nas_acl_apply import apply_folder_permissions, parse_synoacl_get, _run_ssh_commands
from nas_storage.nas_acl_jobs import nas_acl_job_running, spawn_nas_acl_batch_job
from nas_storage.permission_defs import convert_no_delete_except_tgd, detect_preset_from_flags


def dump_groups(path: str) -> None:
    out = _run_ssh_commands([f'/usr/syno/bin/synoacltool -get "{path}"'])
    rows = [r for r in parse_synoacl_get(out) if r['level'] == 0 and r['kind'] == 'group' and r['name']]
    for r in rows:
        dD = r['perm'][4:6] if len(r['perm']) >= 6 else '??'
        print(f'  {r["name"]} {r["perm"]} dD={dD}')


def main() -> None:
    stats = convert_no_delete_except_tgd()
    print('CONVERT', stats)
    counts: dict[str, int] = {}
    for perm in NasFolderPermission.objects.select_related('group'):
        preset = detect_preset_from_flags(perm.permission_flags())
        counts[preset] = counts.get(preset, 0) + 1
        if perm.group and perm.group.name.upper() == 'TGD' and preset != 'full':
            raise SystemExit(f'TGD not full folder={perm.folder_id}')
    print('PRESETS', counts)

    probe = NasShareFolder.objects.filter(share_name='04_KINH_DOANH_CSKH', parent__isnull=True).first()
    result = apply_folder_permissions(probe)
    print('PROBE', result.get('status'), result.get('acl_changed'))
    dump_groups(probe.resolved_volume_path())
    out = _run_ssh_commands([f'/usr/syno/bin/synoacltool -get "{probe.resolved_volume_path()}"'])
    mkt = [r for r in parse_synoacl_get(out) if r['name'].lower().startswith('mkt@') and r['level'] == 0]
    if not mkt or mkt[0]['perm'][4:6] == '--':
        raise SystemExit('MKT still missing delete bits')

    errors = []
    for folder in NasShareFolder.objects.filter(is_active=True, parent__isnull=True).order_by('share_name'):
        try:
            result = apply_folder_permissions(folder)
            print(f'{folder.share_name}: {result.get("status")} acl_changed={result.get("acl_changed")}')
        except Exception as exc:
            errors.append(f'{folder.share_name}: {exc}')
            print('ERR', folder.share_name, exc)
    if errors:
        raise SystemExit(1)

    print('\n=== SAMPLE ===')
    for name in ('04_KINH_DOANH_CSKH', '02_HANH_CHINH_NHAN_SU', '10_HE_THONG_CNTT'):
        folder = NasShareFolder.objects.filter(share_name=name, parent__isnull=True).first()
        print(name)
        dump_groups(folder.resolved_volume_path())

    spawned = False
    if not nas_acl_job_running('apply_nas_acl_all'):
        spawned = spawn_nas_acl_batch_job('apply_nas_acl_all')
    print('SPAWN_ALL', spawned)
    print('ALL_OK')


if __name__ == '__main__':
    main()
