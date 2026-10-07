"""Giới hạn Tuyển dụng theo phạm vi quản lý — giữ nguyên quyền xem toàn bộ cho HCNS & TGĐ.

Sau thay đổi, ai có menu Tuyển dụng chỉ thấy vị trí thuộc phòng ban / bộ phận mình quản lý,
trừ nhóm có quyền bổ sung ``recruitment.extras.all_departments``. Migration này bật quyền đó
cho các nhóm Hành chính nhân sự (``hcns-*``) và Tổng giám đốc (``tgd-*``) đang có quyền Tuyển dụng.
"""

from django.db import migrations

ACTIONS = ('view', 'create', 'update', 'delete', 'export', 'print')
PREFIXES = ('hcns-', 'tgd-')


def _has_recruitment(entry) -> bool:
    if not isinstance(entry, dict):
        return False
    if any(entry.get(a) for a in ACTIONS):
        return True
    menus = entry.get('menus')
    return isinstance(menus, dict) and any(
        isinstance(m, dict) and any(m.get(a) for a in ACTIONS) for m in menus.values()
    )


def forward(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        if not (group.slug or '').startswith(PREFIXES):
            continue
        perms = dict(group.module_permissions or {})
        entry = perms.get('recruitment')
        if not _has_recruitment(entry):
            continue
        entry = dict(entry)
        extras = dict(entry.get('extras') or {})
        extras['all_departments'] = True
        entry['extras'] = extras
        perms['recruitment'] = entry
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment', '0013_job_target_division'),
        ('hrm', '0118_recruitment_under_hrm'),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
