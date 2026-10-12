"""Gỡ menu Tình hình bàn giao khỏi nhóm quyền đã lưu."""

from django.db import migrations


def drop_menu(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        sx = perms.get('san_xuat')
        if not isinstance(sx, dict):
            continue
        menus = sx.get('menus')
        if not isinstance(menus, dict) or 'handover_status' not in menus:
            continue
        menus = dict(menus)
        menus.pop('handover_status', None)
        sx = dict(sx)
        sx['menus'] = menus
        perms['san_xuat'] = sx
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0118_recruitment_under_hrm'),
    ]

    operations = [
        migrations.RunPython(drop_menu, noop_reverse),
    ]
