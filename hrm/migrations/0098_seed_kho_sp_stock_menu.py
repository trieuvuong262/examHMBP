"""Seed menu Tồn kho cho Kho sản phẩm — kế thừa quyền từ Danh mục."""

from django.db import migrations


def _flags(source) -> dict:
    if not isinstance(source, dict):
        source = {}
    return {
        'view': bool(source.get('view')),
        'create': bool(source.get('create')),
        'update': bool(source.get('update')),
        'delete': bool(source.get('delete')),
        'export': bool(source.get('export')),
        'print': bool(source.get('print')),
    }


def _has_any(flags: dict) -> bool:
    return any(flags.get(key) for key in ('view', 'create', 'update', 'delete', 'export', 'print'))


def seed_forward(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        ksp = perms.get('kho_san_pham')
        if not isinstance(ksp, dict):
            continue
        menus = dict(ksp.get('menus') or {}) if isinstance(ksp.get('menus'), dict) else {}
        if 'stock' in menus:
            continue
        source = menus.get('products') or ksp
        flags = _flags(source)
        if not _has_any(flags):
            continue
        menus['stock'] = flags
        ksp['menus'] = menus
        perms['kho_san_pham'] = ksp
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


def seed_backward(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        ksp = perms.get('kho_san_pham')
        if not isinstance(ksp, dict):
            continue
        menus = dict(ksp.get('menus') or {}) if isinstance(ksp.get('menus'), dict) else {}
        if 'stock' not in menus:
            continue
        menus.pop('stock', None)
        ksp['menus'] = menus
        perms['kho_san_pham'] = ksp
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0097_sync_ho_so_ie_menus'),
    ]

    operations = [
        migrations.RunPython(seed_forward, seed_backward),
    ]
