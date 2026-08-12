"""Seed menu: Thiết lập công đoạn (ie_settings) — kế thừa quyền ie."""

from django.db import migrations

NEW_MENU_KEYS = ('ie_settings',)


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
        if 'ie_settings' in menus:
            continue
        source = menus.get('ie') or menus.get('docs') or menus.get('bom') or {}
        template = _menu_template(source, sx)
        if not template['view']:
            continue
        menus['ie_settings'] = template
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
        changed = False
        for key in NEW_MENU_KEYS:
            if key in menus:
                menus.pop(key)
                changed = True
        if changed:
            sx['menus'] = menus
            perms['san_xuat'] = sx
            group.module_permissions = perms
            group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0093_sync_san_xuat_menu_registry'),
    ]

    operations = [
        migrations.RunPython(seed_forward, seed_backward),
    ]
