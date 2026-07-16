"""Cấp KiotViet cho nhóm SX liên quan — menu KV đã chuyển vào Sản xuất."""

from django.db import migrations

KIOTVIET_MENU_KEYS = (
    'customers',
    'orders',
    'invoices',
    'products',
    'stock',
    'purchases',
)

_SX_RELATED_MARKERS = (
    'sx-',
    'sx ',
    'khsx',
    'đbcl',
    'dbcl',
    'sản xuất',
    'san xuat',
    'kế hoạch sản xuất',
    'ke hoach san xuat',
    'đảm bảo chất lượng',
    'dam bao chat luong',
)


def _flags(view=False, create=False, update=False, delete=False, export=False):
    if any((create, update, delete, export)):
        view = True
    return {
        'view': bool(view),
        'create': bool(create),
        'update': bool(update),
        'delete': bool(delete),
        'export': bool(export),
    }


def _is_sx_related(name: str, slug: str) -> bool:
    text = f'{name} {slug}'.casefold()
    return any(m in text for m in _SX_RELATED_MARKERS)


def _ensure_kiotviet(perms: dict) -> tuple[bool, dict]:
    kv = dict(perms.get('kiotviet') or {})
    tpl = _flags(view=True)
    changed = False
    if not kv.get('view'):
        kv = dict(tpl)
        changed = True
    menus = dict(kv.get('menus') or {})
    if not menus:
        kv['menus'] = {key: dict(tpl) for key in KIOTVIET_MENU_KEYS}
        changed = True
    else:
        for key in KIOTVIET_MENU_KEYS:
            if key not in menus:
                menus[key] = dict(tpl)
                changed = True
        kv['menus'] = menus
    for action in ('view', 'create', 'update', 'delete', 'export'):
        kv[action] = any(
            bool((kv.get('menus') or {}).get(k, {}).get(action))
            for k in KIOTVIET_MENU_KEYS
        ) or bool(kv.get(action))
    out = dict(perms)
    out['kiotviet'] = kv
    return changed, out


def forward(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')

    for group in PermissionGroup.objects.all():
        if not _is_sx_related(group.name or '', group.slug or ''):
            continue
        perms = dict(group.module_permissions or {})
        changed, perms = _ensure_kiotviet(perms)
        if changed:
            group.module_permissions = perms
            group.save(update_fields=['module_permissions'])

    for perm in DepartmentMenuPermission.objects.all():
        modules = list(perm.modules or [])
        if 'san_xuat' in modules and 'kiotviet' not in modules:
            modules.append('kiotviet')
            perm.modules = modules
            perm.save(update_fields=['modules'])


def backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0068_sync_san_xuat_npl_permissions'),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
