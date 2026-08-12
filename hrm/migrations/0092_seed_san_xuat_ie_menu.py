"""Seed menu: Công đoạn / định mức (ie) — tách khỏi BOM."""

from django.db import migrations

NEW_MENU_KEYS = ('ie',)


def _menu_template(source, sx):
    if isinstance(source, dict) and source:
        return {
            'view': bool(source.get('view')),
            'create': bool(source.get('create') or source.get('update')),
            'update': bool(source.get('update')),
            'delete': bool(source.get('delete')),
            'export': bool(source.get('export')),
            'print': bool(source.get('print')),
        }
    return {
        'view': bool(sx.get('view')),
        'create': bool(sx.get('create') or sx.get('update')),
        'update': bool(sx.get('update')),
        'delete': bool(sx.get('delete')),
        'export': bool(sx.get('export')),
        'print': bool(sx.get('print')),
    }


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
        # Trước đây sidebar Công đoạn gắn theo quyền BOM — kế thừa để không mất quyền.
        source = menus.get('bom') or menus.get('docs') or menus.get('capacity') or {}
        template = _menu_template(source, sx)
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
        ('hrm', '0091_seed_san_xuat_team_work_goods_menu'),
    ]

    operations = [
        migrations.RunPython(seed_forward, seed_backward),
    ]
