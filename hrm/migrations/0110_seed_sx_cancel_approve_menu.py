"""Seed menu Duyệt hủy sản xuất. Xem được kế thừa; quyền duyệt (update) để trống."""

from django.db import migrations

NEW_MENU_KEYS = ('sx_cancel_approve',)


def seed_forward(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        sx = dict(perms.get('san_xuat') or {})
        menus = dict(sx.get('menus') or {})
        if not menus or 'sx_cancel_approve' in menus:
            continue
        source = menus.get('plan_board') or menus.get('mo') or {}
        if not source.get('view') and not sx.get('view'):
            continue
        menus['sx_cancel_approve'] = {
            'view': True,
            'create': False,
            'update': False,
            'delete': False,
            'export': False,
            'print': False,
        }
        sx['menus'] = menus
        perms['san_xuat'] = sx
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


def seed_backward(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        sx = dict(perms.get('san_xuat') or {})
        menus = dict(sx.get('menus') or {})
        if 'sx_cancel_approve' not in menus:
            continue
        menus.pop('sx_cancel_approve')
        sx['menus'] = menus
        perms['san_xuat'] = sx
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0109_trip_schedule_create_all_hcns_manage'),
    ]

    operations = [
        migrations.RunPython(seed_forward, seed_backward),
    ]
