"""IT được xem và thao tác Bảng so giá + Duyệt giá để vận hành menu trong Kế hoạch SX."""

from django.db import migrations

QUOTE_ON = {
    'view': True,
    'create': True,
    'update': True,
    'delete': False,
    'export': False,
    'print': False,
}
APPROVE_ON = {
    'view': True,
    'create': False,
    'update': True,
    'delete': False,
    'export': False,
    'print': False,
}


def seed_forward(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    group = PermissionGroup.objects.filter(name='IT').first()
    if group is None:
        return
    perms = dict(group.module_permissions or {})
    sx = dict(perms.get('san_xuat') or {})
    menus = dict(sx.get('menus') or {})
    sx['view'] = True
    menus['sx_price_quote'] = dict(QUOTE_ON)
    menus['sx_price_approve'] = dict(APPROVE_ON)
    sx['menus'] = menus
    perms['san_xuat'] = sx
    group.module_permissions = perms
    group.save(update_fields=['module_permissions'])


def seed_backward(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    group = PermissionGroup.objects.filter(name='IT').first()
    if group is None:
        return
    perms = dict(group.module_permissions or {})
    sx = dict(perms.get('san_xuat') or {})
    menus = dict(sx.get('menus') or {})
    off = {key: False for key in QUOTE_ON}
    menus['sx_price_quote'] = dict(off)
    menus['sx_price_approve'] = dict(off)
    sx['menus'] = menus
    perms['san_xuat'] = sx
    group.module_permissions = perms
    group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0116_narrow_price_approve_permissions'),
    ]

    operations = [
        migrations.RunPython(seed_forward, seed_backward),
    ]
