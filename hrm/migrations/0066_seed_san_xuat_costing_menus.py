"""Seed menu con Giá thành kế hoạch."""

from django.db import migrations

NEW_MENU_KEYS = (
    'costing_norm',
    'costing_so',
)


def _seed(perms_dict):
    sx = dict(perms_dict.get('san_xuat') or {})
    if not sx:
        return False, perms_dict
    menus = dict(sx.get('menus') or {})
    if not menus:
        return False, perms_dict

    source = menus.get('costing_hub') or menus.get('costing') or menus.get('docs')
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
        ('hrm', '0065_seed_san_xuat_qc_menus'),
    ]

    operations = [
        migrations.RunPython(seed_forward, seed_backward),
    ]
