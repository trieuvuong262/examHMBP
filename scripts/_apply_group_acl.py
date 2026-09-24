"""Apply group-only synoacl (NAS-style) and sample-check."""
from __future__ import annotations

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
django.setup()

from nas_storage.models import NasShareFolder
from nas_storage.nas_acl_apply import apply_folder_permissions, parse_synoacl_get, _run_ssh_commands
from nas_storage.nas_acl_jobs import nas_acl_job_running, spawn_nas_acl_batch_job


def dump_groups(path: str) -> None:
    out = _run_ssh_commands([f'/usr/syno/bin/synoacltool -get "{path}"'])
    rows = parse_synoacl_get(out)
    users = [r for r in rows if r['kind'] == 'user' and r['level'] == 0]
    groups = [r for r in rows if r['kind'] == 'group' and r['level'] == 0]
    print(f'  groups={len(groups)} users={len(users)}')
    for r in groups:
        print(f'    G {r["name"]} {r["perm"]}')
    for r in users[:8]:
        print(f'    U {r["name"]} {r["perm"]}')
    if len(users) > 8:
        print(f'    ... {len(users) - 8} more users')


def main() -> None:
    probe = NasShareFolder.objects.filter(share_name='02_HANH_CHINH_NHAN_SU', parent__isnull=True).first()
    result = apply_folder_permissions(probe)
    print('PROBE', result.get('status'), 'acl_changed=', result.get('acl_changed'))
    dump_groups(probe.resolved_volume_path())

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
    for name in ('02_HANH_CHINH_NHAN_SU', '04_KINH_DOANH_CSKH', '07_SAN_XUAT'):
        folder = NasShareFolder.objects.filter(share_name=name, parent__isnull=True).first()
        print(name)
        dump_groups(folder.resolved_volume_path())

    if errors:
        raise SystemExit(1)
    spawned = False
    if not nas_acl_job_running('apply_nas_acl_all'):
        spawned = spawn_nas_acl_batch_job('apply_nas_acl_all')
    print('SPAWN_ALL', spawned)


if __name__ == '__main__':
    main()
