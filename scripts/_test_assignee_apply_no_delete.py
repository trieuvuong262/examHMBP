"""Test assignee group/user form, then apply no-delete except TGD."""
from __future__ import annotations

import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')
import django
django.setup()

from nas_storage.forms import NasFolderPermissionForm
from nas_storage.models import NasFolderPermission, NasShareFolder
from nas_storage.nas_acl_apply import apply_folder_permissions, parse_synoacl_get, _run_ssh_commands
from nas_storage.nas_acl_jobs import nas_acl_job_running, spawn_nas_acl_batch_job
from nas_storage.permission_defs import (
    convert_no_delete_except_tgd,
    detect_preset_from_flags,
)


def _flags(*names: str, extra=None):
    from nas_storage.permission_defs import ALL_PERM_FIELD_NAMES, flags_from_preset

    data = {name: False for name in ALL_PERM_FIELD_NAMES}
    data.update(flags_from_preset('read_write_no_delete'))
    if extra:
        data.update(extra)
    return data


def test_assignee_forms() -> None:
    folder = NasShareFolder.objects.filter(pk=10).first() or NasShareFolder.objects.filter(
        share_name='04_KINH_DOANH_CSKH', parent__isnull=True
    ).first()
    assert folder, 'missing folder 10'
    perm17 = NasFolderPermission.objects.filter(pk=17, folder=folder).select_related('group', 'user').first()
    assert perm17, 'missing perm 17'
    assert perm17.group_id and perm17.group.name == 'TGD', perm17
    assert perm17.user_id is None
    form = NasFolderPermissionForm(instance=perm17, folder=folder)
    assert form.fields['assignee_type'].initial == 'group'
    print('PERM17_OK', folder.share_name, perm17.group.name, detect_preset_from_flags(perm17.permission_flags()))

    probe_form = NasFolderPermissionForm(folder=folder)
    group = probe_form.fields['group'].queryset.first()
    user = probe_form.fields['user'].queryset.first()
    assert group and user, (group, user)

    flags = _flags()
    group_data = {
        'assignee_type': 'group',
        'group': str(group.pk),
        'user': str(user.pk),  # must be ignored
        'permission_type': 'allow',
        'apply_to': 'all',
        'preset': 'read_write_no_delete',
        **{k: 'on' for k, v in flags.items() if v},
    }
    gform = NasFolderPermissionForm(group_data, folder=folder)
    assert gform.is_valid(), gform.errors
    assert gform.cleaned_data['group'] == group
    assert gform.cleaned_data['user'] is None
    print('GROUP_FORM_OK', group.name, 'ignored user', user.username)

    user_data = {
        'assignee_type': 'user',
        'group': str(group.pk),  # must be ignored
        'user': str(user.pk),
        'permission_type': 'allow',
        'apply_to': 'all',
        'preset': 'read_write_no_delete',
        **{k: 'on' for k, v in flags.items() if v},
    }
    uform = NasFolderPermissionForm(user_data, folder=folder)
    assert uform.is_valid(), uform.errors
    assert uform.cleaned_data['user'] == user
    assert uform.cleaned_data['group'] is None
    print('USER_FORM_OK', user.username, 'ignored group', group.name)

    missing_group = dict(group_data)
    missing_group['group'] = ''
    bad = NasFolderPermissionForm(missing_group, folder=folder)
    assert not bad.is_valid()
    assert 'group' in bad.errors
    print('GROUP_REQUIRED_OK')

    missing_user = dict(user_data)
    missing_user['user'] = ''
    bad_u = NasFolderPermissionForm(missing_user, folder=folder)
    assert not bad_u.is_valid()
    assert 'user' in bad_u.errors
    print('USER_REQUIRED_OK')

    # persist + rollback user grant
    perm = uform.save(commit=False)
    perm.folder = folder
    perm.save()
    stored = NasFolderPermission.objects.get(pk=perm.pk)
    assert stored.user_id == user.pk
    assert stored.group_id is None
    assert detect_preset_from_flags(stored.permission_flags()) == 'read_write_no_delete'
    stored.delete()
    print('USER_SAVE_XOR_OK')


def dump_groups(path: str) -> None:
    out = _run_ssh_commands([f'/usr/syno/bin/synoacltool -get "{path}"'])
    rows = [r for r in parse_synoacl_get(out) if r['level'] == 0 and r['kind'] == 'group' and r['name']]
    for r in rows:
        dD = r['perm'][4:6] if len(r['perm']) >= 6 else '??'
        print(f'  {r["name"]} {r["perm"]} dD={dD}')


def main() -> None:
    test_assignee_forms()
    stats = convert_no_delete_except_tgd()
    print('CONVERT', stats)
    counts: dict[str, int] = {}
    tgd_bad = []
    for perm in NasFolderPermission.objects.select_related('group'):
        preset = detect_preset_from_flags(perm.permission_flags())
        counts[preset] = counts.get(preset, 0) + 1
        if perm.group and perm.group.name.upper() == 'TGD' and preset != 'full':
            tgd_bad.append((perm.folder_id, preset))
    print('PRESETS', counts)
    if tgd_bad:
        raise SystemExit(f'TGD not full: {tgd_bad[:10]}')

    probe = NasShareFolder.objects.filter(share_name='04_KINH_DOANH_CSKH', parent__isnull=True).first()
    result = apply_folder_permissions(probe)
    print('PROBE', result.get('status'), result.get('acl_changed'))
    dump_groups(probe.resolved_volume_path())

    errors = []
    roots = NasShareFolder.objects.filter(is_active=True, parent__isnull=True).order_by('share_name')
    for folder in roots:
        try:
            result = apply_folder_permissions(folder)
            print(f'{folder.share_name}: {result.get("status")} acl_changed={result.get("acl_changed")}')
        except Exception as exc:
            errors.append(f'{folder.share_name}: {exc}')
            print('ERR', folder.share_name, exc)
    if errors:
        raise SystemExit(1)

    print('\n=== SAMPLE ===')
    for name in ('04_KINH_DOANH_CSKH', '02_HANH_CHINH_NHAN_SU', '10_HE_THONG_CNTT', '00_QUY_DINH_CHUNG'):
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
