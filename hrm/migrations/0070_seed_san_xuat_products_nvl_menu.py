"""Seed menu con Sản phẩm, NVL (landing catalog)."""

from django.db import migrations

NEW_MENU_KEYS = (
    'products_nvl',
)


def _seed(perms_dict):
    sx = dict(perms_dict.get('san_xuat') or {})
    if not sx:
        return False, perms_dict
    menus = dict(sx.get('menus') or {})
    if not menus:
        return False, perms_dict

    source = (
        menus.get('docs')
        or menus.get('bom')
        or menus.get('fg_stock')
        or menus.get('overview')
    )
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
    if not changed:
        return False, perms_dict
    sx['menus'] = menus
    out = dict(perms_dict)
    out['san_xuat'] = sx
    return True, out


def seed_forward(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        changed, new_perms = _seed(perms)
        if changed:
            group.module_permissions = new_perms
            group.save(update_fields=['module_permissions'])


def seed_backward(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        sx = dict(perms.get('san_xuat') or {})
        menus = dict(sx.get('menus') or {})
        if not menus:
            continue
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
        ('hrm', '0069_sync_kiotviet_under_san_xuat'),
    ]

    operations = [
        migrations.RunPython(seed_forward, seed_backward),
    ]
