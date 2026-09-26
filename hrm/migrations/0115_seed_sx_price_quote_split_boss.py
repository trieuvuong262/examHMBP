"""Tách menu Bảng so giá (KHSX) và Duyệt giá (Sếp)."""

from django.db import migrations

QUOTE_KEY = 'sx_price_quote'
APPROVE_KEY = 'sx_price_approve'

_BOSS_NAME_MARKERS = (
    'giám đốc',
    'giam doc',
    'sếp',
    'sep duc',
    'sếp đức',
)


def _is_boss_group(name: str) -> bool:
    n = (name or '').casefold()
    return any(m in n for m in _BOSS_NAME_MARKERS)


def seed_forward(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        sx = dict(perms.get('san_xuat') or {})
        menus = dict(sx.get('menus') or {})
        if not menus and not sx.get('view'):
            continue
        changed = False
        npl = menus.get('npl_pr') or {}
        approve = dict(menus.get(APPROVE_KEY) or {})

        # KHSX: bảng so giá
        if QUOTE_KEY not in menus:
            if npl.get('view') or approve.get('view') or sx.get('view'):
                menus[QUOTE_KEY] = {
                    'view': True,
                    'create': True,
                    'update': True,
                    'delete': False,
                    'export': False,
                    'print': False,
                }
                changed = True

        # Sếp: giữ/duyệt trên Duyệt giá; NV thường bỏ view Duyệt giá
        if _is_boss_group(group.name):
            menus[APPROVE_KEY] = {
                'view': True,
                'create': False,
                'update': True,
                'delete': False,
                'export': False,
                'print': False,
            }
            changed = True
        elif APPROVE_KEY in menus:
            # Nhân viên KHSX không thấy menu Duyệt giá (Sếp)
            if npl.get('view') and not approve.get('update'):
                menus[APPROVE_KEY] = {
                    'view': False,
                    'create': False,
                    'update': False,
                    'delete': False,
                    'export': False,
                    'print': False,
                }
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
        if QUOTE_KEY not in menus:
            continue
        menus.pop(QUOTE_KEY, None)
        sx['menus'] = menus
        perms['san_xuat'] = sx
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0114_seed_sx_price_approve_menu'),
    ]

    operations = [
        migrations.RunPython(seed_forward, seed_backward),
    ]
