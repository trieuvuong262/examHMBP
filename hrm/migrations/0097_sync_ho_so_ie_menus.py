"""Đồng bộ menu Hồ sơ / công đoạn trong nhóm quyền cho khớp sidebar.

Bổ sung ``ie_approve`` / ``ie_settings`` còn thiếu; kế thừa từ ``ie`` / ``docs`` / ``bom``.
"""

from django.db import migrations

# Khớp cụm Hồ sơ trên sidebar (không gồm bom/products_nvl đã ẩn/gộp).
HO_SO_MENU_KEYS = (
    'docs',
    'ie',
    'ie_approve',
    'ie_settings',
    'capacity',
)

INHERIT_FROM = {
    'ie': ('docs', 'bom', 'capacity'),
    'ie_approve': ('ie', 'ie_settings', 'docs'),
    'ie_settings': ('ie', 'docs', 'bom'),
    'docs': ('bom', 'ie', 'capacity'),
    'capacity': ('docs', 'ie', 'bom'),
}


def _flags_from(entry: dict) -> dict:
    return {
        'view': bool(entry.get('view')),
        'create': bool(entry.get('create') or entry.get('update')),
        'update': bool(entry.get('update')),
        'delete': bool(entry.get('delete')),
        'export': bool(entry.get('export')),
        'print': bool(entry.get('print')),
    }


def _resolve_template(menus: dict, key: str, sx: dict) -> dict:
    for src in INHERIT_FROM.get(key, ()):
        src_menu = menus.get(src)
        if isinstance(src_menu, dict) and src_menu.get('view'):
            return _flags_from(src_menu)
    for menu in menus.values():
        if isinstance(menu, dict) and menu.get('view'):
            return _flags_from(menu)
    return _flags_from(sx)


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
        changed = False
        for key in HO_SO_MENU_KEYS:
            if key in menus:
                continue
            menus[key] = _resolve_template(menus, key, sx)
            changed = True
        if changed:
            sx['menus'] = menus
            for action in ('view', 'create', 'update', 'delete', 'export', 'print'):
                sx[action] = any(
                    bool((menus.get(k) or {}).get(action)) for k in menus
                ) or bool(sx.get(action))
            perms['san_xuat'] = sx
            group.module_permissions = perms
            group.save(update_fields=['module_permissions'])


def seed_backward(apps, schema_editor):
    # Không gỡ — chỉ đồng bộ forward.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0096_seed_hrm_locked_accounts_menu'),
    ]

    operations = [
        migrations.RunPython(seed_forward, seed_backward),
    ]
