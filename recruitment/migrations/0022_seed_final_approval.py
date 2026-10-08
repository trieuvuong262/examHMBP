"""Duyệt cấp 2 sau phỏng vấn.

* Kết quả «Đạt» có trước khi có cấp 2 coi như đã duyệt — không kẹt hồ sơ cũ.
* Bật quyền bổ sung ``recruitment.extras.final_approve`` cho nhóm Tổng giám đốc (``tgd-*``)
  đang có quyền Tuyển dụng. superuser / admin luôn duyệt được.
"""

from django.db import migrations

ACTIONS = ('view', 'create', 'update', 'delete', 'export', 'print')


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
    Interview = apps.get_model('recruitment', 'Interview')
    Interview.objects.filter(result='pass', final_result='').update(final_result='pass')

    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.filter(slug__startswith='tgd-'):
        perms = dict(group.module_permissions or {})
        entry = perms.get('recruitment')
        if not _has_recruitment(entry):
            continue
        entry = dict(entry)
        entry['extras'] = {**(entry.get('extras') or {}), 'final_approve': True}
        perms['recruitment'] = entry
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment', '0021_interview_final_approval'),
        ('hrm', '0118_recruitment_under_hrm'),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
