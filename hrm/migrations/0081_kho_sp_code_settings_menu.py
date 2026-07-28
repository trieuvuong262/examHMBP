from django.db import migrations


def _flags(**kwargs):
    return {
        'view': bool(kwargs.get('view')),
        'create': bool(kwargs.get('create')),
        'update': bool(kwargs.get('update')),
        'delete': bool(kwargs.get('delete')),
        'export': bool(kwargs.get('export')),
    }


def add_code_settings_menu(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        ksp = perms.get('kho_san_pham')
        if not isinstance(ksp, dict):
            continue
        menus = dict(ksp.get('menus') or {})
        if 'code_settings' in menus:
            continue
        products = menus.get('products') or {
            'view': bool(ksp.get('view')),
            'create': bool(ksp.get('create')),
            'update': bool(ksp.get('update')),
            'delete': bool(ksp.get('delete')),
            'export': bool(ksp.get('export')),
        }
        menus['code_settings'] = dict(products)
        ksp['menus'] = menus
        perms['kho_san_pham'] = ksp
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


def remove_code_settings_menu(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        ksp = perms.get('kho_san_pham')
        if not isinstance(ksp, dict):
            continue
        menus = dict(ksp.get('menus') or {})
        if 'code_settings' not in menus:
            continue
        menus.pop('code_settings', None)
        ksp['menus'] = menus
        perms['kho_san_pham'] = ksp
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0080_add_kho_san_pham_module'),
    ]

    operations = [
        migrations.RunPython(add_code_settings_menu, remove_code_settings_menu),
    ]
