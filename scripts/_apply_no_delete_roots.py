"""Convert remaining RW, apply no-delete synoacl, verify sample shares."""
from __future__ import annotations

import os
import sys

if __name__ == '__main__' and 'django' not in sys.modules:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
    import django
    django.setup()

from nas_storage.models import NasFolderPermission, NasShareFolder
from nas_storage.nas_acl_apply import (
    PRESERVED_SHARE_PRINCIPAL_KEYS,
    _active_folder_permissions,
    _desired_synoacl_aces_for_permissions,
    _parse_synoacl_ace,
    _run_ssh_commands,
    _synoacl_key,
    apply_folder_permissions,
    parse_synoacl_get,
    principal_group_key,
)
from nas_storage.nas_acl_jobs import nas_acl_job_running, spawn_nas_acl_batch_job
from nas_storage.permission_defs import (
    detect_preset_from_flags,
    convert_read_write_permissions_to_no_delete,
)

SAMPLE_SHARES = (
    '04_KINH_DOANH_CSKH',
    '02_HANH_CHINH_NHAN_SU',
    '07_SAN_XUAT',
    '00_QUY_DINH_CHUNG',
    '10_HE_THONG_CNTT',
)


def acl_rows(path: str) -> list[dict]:
    out = _run_ssh_commands([f'/usr/syno/bin/synoacltool -get "{path}"'])
    return [r for r in parse_synoacl_get(out) if r['level'] == 0 and r['action'] == 'allow']


def verify_folder(folder) -> list[str]:
    errors: list[str] = []
    path = folder.resolved_volume_path()
    rows = acl_rows(path)
    by_key: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        if not row['name']:
            errors.append(f'{folder.share_name}: empty-name ACE idx={row["index"]} perm={row["perm"]}')
            continue
        if principal_group_key(row['name']) in PRESERVED_SHARE_PRINCIPAL_KEYS:
            continue
        by_key.setdefault(_synoacl_key(row['kind'], row['name']), []).append(row)

    perms = list(_active_folder_permissions(folder))
    desired = _desired_synoacl_aces_for_permissions(perms)
    desired_by_key = {}
    for ace in desired:
        parsed = _parse_synoacl_ace(ace)
        if parsed and parsed['name']:
            desired_by_key[_synoacl_key(parsed['kind'], parsed['name'])] = ace

    for key, ace in desired_by_key.items():
        kind, name = key
        matches = by_key.get(key) or []
        if kind != 'group':
            if len(matches) > 1:
                errors.append(f'{folder.share_name}: {kind}:{name} duplicate={len(matches)}')
            elif len(matches) == 1:
                actual = f'{matches[0]["kind"]}:{matches[0]["name"]}:{matches[0]["action"]}:{matches[0]["perm"]}:{matches[0]["inherit"]}'
                if actual != ace:
                    errors.append(
                        f'{folder.share_name}: {kind}:{name}\n    want {ace}\n    got  {actual}'
                    )
            continue
        if len(matches) != 1:
            errors.append(f'{folder.share_name}: {kind}:{name} count={len(matches)} expected=1')
            continue
        actual = f'{matches[0]["kind"]}:{matches[0]["name"]}:{matches[0]["action"]}:{matches[0]["perm"]}:{matches[0]["inherit"]}'
        if actual != ace:
            errors.append(
                f'{folder.share_name}: {kind}:{name}\n    want {ace}\n    got  {actual}'
            )

    # Group-level delete bits vs Portal preset
    for perm in perms:
        if not perm.group_id:
            continue
        preset = detect_preset_from_flags(perm.permission_flags())
        name = (perm.resolved_nas_principal() or '').lstrip('@')
        matches = by_key.get(_synoacl_key('group', name)) or []
        if not matches:
            continue
        dD = matches[0]['perm'][4:6] if len(matches[0]['perm']) >= 6 else '??'
        if preset in {'read', 'read_write_no_delete'} and dD != '--':
            errors.append(f'{folder.share_name}: group {name} preset={preset} still has delete bits {dD}')
        if preset in {'full', 'read_write'} and 'd' not in dD.lower() and 'd' not in matches[0]['perm'][4:6]:
            errors.append(f'{folder.share_name}: group {name} preset={preset} missing delete bits {dD}')
        if preset in {'full', 'read_write'} and dD == '--':
            errors.append(f'{folder.share_name}: group {name} preset={preset} missing delete bits {dD}')

    return errors


def print_groups(folder) -> None:
    rows = acl_rows(folder.resolved_volume_path())
    print(f'\n{folder.share_name}')
    seen = set()
    for row in rows:
        if row['kind'] != 'group':
            continue
        dD = row['perm'][4:6] if len(row['perm']) >= 6 else '??'
        mark = ' DUP' if row['name'] in seen else ''
        seen.add(row['name'])
        print(f'  [{row["index"]}] {row["name"] or "(empty)"} {row["perm"]} dD={dD}{mark}')


def main() -> None:
    converted = convert_read_write_permissions_to_no_delete()
    counts = {}
    for perm in NasFolderPermission.objects.iterator():
        preset = detect_preset_from_flags(perm.permission_flags())
        counts[preset] = counts.get(preset, 0) + 1
    print('CONVERTED', converted)
    print('PRESETS', counts)

    probe = NasShareFolder.objects.filter(share_name='02_HANH_CHINH_NHAN_SU', parent__isnull=True).first()
    if not probe:
        raise SystemExit('missing 02_HANH_CHINH_NHAN_SU')
    result = apply_folder_permissions(probe)
    print('PROBE', probe.share_name, result.get('status'), 'acl_changed=', result.get('acl_changed'))
    probe_errors = verify_folder(probe)
    print_groups(probe)
    if probe_errors:
        print('PROBE_FAIL')
        for err in probe_errors:
            print(err)
        raise SystemExit(2)
    print('PROBE_OK')

    roots = list(
        NasShareFolder.objects.filter(is_active=True, parent__isnull=True).order_by('sort_order', 'share_name')
    )
    print('ROOTS', len(roots))
    errors = []
    for folder in roots:
        try:
            result = apply_folder_permissions(folder)
            print(f'{folder.share_name}: {result.get("status")} acl_changed={result.get("acl_changed")}')
            errors.extend(verify_folder(folder))
        except Exception as exc:
            errors.append(f'{folder.share_name}: {exc}')
            print('ERR', folder.share_name, exc)

    print('\n=== SAMPLE ===')
    for name in SAMPLE_SHARES:
        folder = NasShareFolder.objects.filter(share_name=name, parent__isnull=True).first()
        if folder:
            print_groups(folder)

    if errors:
        print('\nVERIFY_FAIL', len(errors))
        for err in errors[:40]:
            print(err)
        raise SystemExit(1)

    print('\nROOTS_VERIFIED')
    running = nas_acl_job_running('apply_nas_acl_all')
    print('JOB_RUNNING', running)
    spawned = False
    if not running:
        spawned = spawn_nas_acl_batch_job('apply_nas_acl_all')
    print('SPAWN_ALL', spawned)


if __name__ == '__main__':
    main()
