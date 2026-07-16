"""Seed submenu hub SX mới cho nhóm đã cấu hình menus san_xuat."""

from django.db import migrations

NEW_MENU_KEYS = (
    'overview',
    'orders',
    'plan',
    'dispatch',
    'qc',
    'costing_hub',
    'fg_stock',
    'npl_stock',
    'process',
)


def _seed_san_xuat_menus(perms_dict):
    """Trả về (changed, new_perms) — copy từ docs/bom/costing hoặc view module."""
    sx = dict(perms_dict.get('san_xuat') or {})
    if not sx:
        return False, perms_dict
    menus = dict(sx.get('menus') or {})
    if not menus:
        # Chưa cấu hình menu con → kế thừa module; không cần seed
        return False, perms_dict

    source = (
        menus.get('docs')
        or menus.get('bom')
        or menus.get('costing')
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


def seed_hub_menus(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        changed, new_perms = _seed_san_xuat_menus(perms)
        if changed:
            group.module_permissions = new_perms
            group.save(update_fields=['module_permissions'])


def unseed_hub_menus(apps, schema_editor):
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
        ('hrm', '0061_add_san_xuat_module'),
    ]

    operations = [
        migrations.RunPython(seed_hub_menus, unseed_hub_menus),
    ]
