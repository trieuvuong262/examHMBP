"""Seed menu con P3: Tải năng lực theo tổ."""

from django.db import migrations

NEW_MENU_KEYS = ('capacity_load',)


def seed_forward(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        sx = dict(perms.get('san_xuat') or {})
        if not sx:
            continue
        menus = dict(sx.get('menus') or {})
        if not menus:
            continue
        source = menus.get('capacity') or menus.get('plan') or {}
        if isinstance(source, dict) and source:
            template = {
                'view': bool(source.get('view')),
                'create': bool(source.get('create')),
                'update': bool(source.get('update')),
                'delete': bool(source.get('delete')),
                'export': bool(source.get('export')),
            }
        else:
            template = {
                'view': bool(sx.get('view')),
                'create': bool(sx.get('create')),
                'update': bool(sx.get('update')),
                'delete': bool(sx.get('delete')),
                'export': bool(sx.get('export')),
            }
        changed = False
        for key in NEW_MENU_KEYS:
            if key not in menus:
                menus[key] = dict(template)
                changed = True
        if changed:
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
        if not menus:
            continue
        removed = False
        for key in NEW_MENU_KEYS:
            if key in menus:
                menus.pop(key)
                removed = True
        if removed:
            sx['menus'] = menus
            perms['san_xuat'] = sx
            group.module_permissions = perms
            group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0083_seed_san_xuat_p2_plan_menus'),
    ]

    operations = [
        migrations.RunPython(seed_forward, seed_backward),
    ]
