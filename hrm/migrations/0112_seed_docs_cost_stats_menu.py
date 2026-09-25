"""Seed menu Thống kê chi phí (Hồ sơ sản phẩm) — view/export, kế thừa từ docs."""

from django.db import migrations

MENU_KEY = 'docs_cost_stats'


def seed_forward(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        sx = dict(perms.get('san_xuat') or {})
        menus = dict(sx.get('menus') or {})
        if not menus or MENU_KEY in menus:
            continue
        source = menus.get('docs') or {}
        if not source.get('view') and not sx.get('view'):
            continue
        menus[MENU_KEY] = {
            'view': bool(source.get('view') or sx.get('view')),
            'create': False,
            'update': False,
            'delete': False,
            'export': bool(source.get('export') or sx.get('export')),
            'print': False,
        }
        sx['menus'] = menus
        for action in ('view', 'export'):
            sx[action] = any(
                bool((menus.get(k) or {}).get(action)) for k in menus
            ) or bool(sx.get(action))
        perms['san_xuat'] = sx
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


def seed_backward(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        sx = dict(perms.get('san_xuat') or {})
        menus = dict(sx.get('menus') or {})
        if MENU_KEY not in menus:
            continue
        menus.pop(MENU_KEY)
        sx['menus'] = menus
        perms['san_xuat'] = sx
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0111_sx_cancel_approve_view_only'),
    ]

    operations = [
        migrations.RunPython(seed_forward, seed_backward),
    ]
