"""Seed menu Duyệt giá. Xem được kế thừa; quyền duyệt (update) để trống."""

from django.db import migrations

NEW_KEY = 'sx_price_approve'


def seed_forward(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        sx = dict(perms.get('san_xuat') or {})
        menus = dict(sx.get('menus') or {})
        if not menus or NEW_KEY in menus:
            continue
        source = menus.get('sx_cancel_approve') or menus.get('npl_pr') or {}
        if not source.get('view') and not sx.get('view'):
            continue
        menus[NEW_KEY] = {
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
        if NEW_KEY not in menus:
            continue
        menus.pop(NEW_KEY)
        sx['menus'] = menus
        perms['san_xuat'] = sx
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0113_ksk_manage_hcns'),
    ]

    operations = [
        migrations.RunPython(seed_forward, seed_backward),
    ]
