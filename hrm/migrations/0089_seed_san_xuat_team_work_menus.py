"""Seed menu: Công việc tổ + 6 submenu theo bộ phận."""

from django.db import migrations

NEW_MENU_KEYS = (
    'team_work',
    'team_work_cat',
    'team_work_inep',
    'team_work_theu',
    'team_work_may',
    'team_work_ht',
    'team_work_gh',
)


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
        source = (
            menus.get('work_assign')
            or menus.get('prod_stats')
            or menus.get('dispatch')
            or menus.get('mo')
            or {}
        )
        if isinstance(source, dict) and source:
            template = {
                'view': bool(source.get('view')),
                'create': bool(source.get('create') or source.get('update')),
                'update': bool(source.get('update')),
                'delete': bool(source.get('delete')),
                'export': bool(source.get('export')),
            }
        else:
            template = {
                'view': bool(sx.get('view')),
                'create': bool(sx.get('create') or sx.get('update')),
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
        ('hrm', '0088_seed_san_xuat_plan_board_menu'),
    ]

    operations = [
        migrations.RunPython(seed_forward, seed_backward),
    ]
