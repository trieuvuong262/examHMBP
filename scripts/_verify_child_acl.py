"""Verify no-delete bits on sample child folders after batch apply."""
from __future__ import annotations

import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
import django
django.setup()

from nas_storage.models import NasShareFolder
from nas_storage.nas_acl_apply import (
    PRESERVED_SHARE_PRINCIPAL_KEYS,
    _active_folder_permissions,
    _desired_synoacl_aces_for_permissions,
    _parse_synoacl_ace,
    _run_ssh_commands,
    _synoacl_key,
    parse_synoacl_get,
    principal_group_key,
)
from nas_storage.permission_defs import detect_preset_from_flags


def acl_rows(path: str) -> list[dict]:
    out = _run_ssh_commands([f'/usr/syno/bin/synoacltool -get "{path}"'])
    return [r for r in parse_synoacl_get(out) if r['level'] == 0 and r['action'] == 'allow']


def verify_folder(folder) -> list[str]:
    errors: list[str] = []
    rows = acl_rows(folder.resolved_volume_path())
    by_key: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        if not row['name']:
            errors.append(f'{folder.portal_path_label()}: empty ACE {row["perm"]}')
            continue
        if principal_group_key(row['name']) in PRESERVED_SHARE_PRINCIPAL_KEYS:
            continue
        by_key.setdefault(_synoacl_key(row['kind'], row['name']), []).append(row)

    perms = list(_active_folder_permissions(folder))
    desired_by_key = {}
    for ace in _desired_synoacl_aces_for_permissions(perms):
        parsed = _parse_synoacl_ace(ace)
        if parsed and parsed['name']:
            desired_by_key[_synoacl_key(parsed['kind'], parsed['name'])] = ace

    for perm in perms:
        if not perm.group_id:
            continue
        preset = detect_preset_from_flags(perm.permission_flags())
        name = (perm.resolved_nas_principal() or '').lstrip('@')
        matches = by_key.get(_synoacl_key('group', name)) or []
        label = folder.portal_path_label()
        if len(matches) != 1:
            errors.append(f'{label}: group {name} count={len(matches)} preset={preset}')
            continue
        dD = matches[0]['perm'][4:6] if len(matches[0]['perm']) >= 6 else '??'
        if preset in {'read', 'read_write_no_delete'} and dD != '--':
            errors.append(f'{label}: {name} preset={preset} dD={dD}')
        if preset in {'full', 'read_write'} and dD == '--':
            errors.append(f'{label}: {name} preset={preset} missing delete dD={dD}')
    return errors


def main() -> None:
    samples = list(
        NasShareFolder.objects.filter(is_active=True, parent__isnull=False).order_by('id')[:12]
    )
    roots = list(NasShareFolder.objects.filter(is_active=True, parent__isnull=True).order_by('share_name'))
    errors = []
    print('CHILDREN', len(samples), 'of', NasShareFolder.objects.filter(is_active=True, parent__isnull=False).count())
    for folder in [*roots, *samples]:
        try:
            errs = verify_folder(folder)
        except Exception as exc:
            errs = [f'{folder.portal_path_label()}: {exc}']
        print(folder.portal_path_label(), 'OK' if not errs else 'FAIL')
        errors.extend(errs)
        if errs:
            for err in errs[:5]:
                print(' ', err)
    if errors:
        print('VERIFY_FAIL', len(errors))
        raise SystemExit(1)
    print('CHILDREN_AND_ROOTS_OK')


if __name__ == '__main__':
    main()
