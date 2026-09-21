"""Đưa Kho vật tư vào stack Sản xuất — cấp quyền cho nhóm đã có Kho NPL."""

from django.db import migrations

VAT_TU_MENU_KEYS = (
    'materials',
    'material_stock',
    'stock_cards',
    'receipts',
    'issues',
    'transfers',
    'disposals',
    'adjustments',
    'reports',
    'settings',
)


def _flags(source=None):
    source = source or {}
    return {
        'view': bool(source.get('view')),
        'create': bool(source.get('create')),
        'update': bool(source.get('update')),
        'delete': bool(source.get('delete')),
        'export': bool(source.get('export')),
        'print': bool(source.get('print')),
    }


def add_kho_vat_tu(apps, schema_editor):
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')
    RoleModulePermission = apps.get_model('hrm', 'RoleModulePermission')
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')

    for perm in DepartmentMenuPermission.objects.all():
        modules = list(perm.modules or [])
        if 'kho_vat_tu' in modules:
            continue
        if 'san_xuat' in modules or 'kho_npl' in modules:
            modules.append('kho_vat_tu')
            perm.modules = modules
            perm.save(update_fields=['modules'])

    role_defaults = {
        'EMPLOYEE': {'view': True, 'edit': False},
        'TEAM_LEADER': {'view': True, 'edit': True},
        'DIVISION_HEAD': {'view': True, 'edit': True},
        'DEPARTMENT_HEAD': {'view': True, 'edit': True},
        'DIRECTOR': {'view': True, 'edit': True},
    }
    for row in RoleModulePermission.objects.all():
        perms = dict(row.module_permissions or {})
        if 'kho_vat_tu' not in perms:
            perms['kho_vat_tu'] = role_defaults.get(row.role, {'view': True, 'edit': False})
            row.module_permissions = perms
            row.save(update_fields=['module_permissions'])

    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        if 'kho_vat_tu' in perms:
            continue
        npl = perms.get('kho_npl') if isinstance(perms.get('kho_npl'), dict) else {}
        sx = perms.get('san_xuat') if isinstance(perms.get('san_xuat'), dict) else {}
        if not npl.get('view') and not sx.get('view'):
            continue
        source = npl if npl.get('view') else sx
        base = _flags(source)
        npl_menus = npl.get('menus') if isinstance(npl.get('menus'), dict) else {}
        menus = {}
        for key in VAT_TU_MENU_KEYS:
            menus[key] = _flags(npl_menus.get(key) or source)
        perms['kho_vat_tu'] = {**base, 'menus': menus}
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


def remove_kho_vat_tu(apps, schema_editor):
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')
    RoleModulePermission = apps.get_model('hrm', 'RoleModulePermission')
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')

    for perm in DepartmentMenuPermission.objects.all():
        modules = [m for m in (perm.modules or []) if m != 'kho_vat_tu']
        if modules != list(perm.modules or []):
            perm.modules = modules
            perm.save(update_fields=['modules'])

    for row in RoleModulePermission.objects.all():
        perms = dict(row.module_permissions or {})
        if 'kho_vat_tu' in perms:
            perms.pop('kho_vat_tu', None)
            row.module_permissions = perms
            row.save(update_fields=['module_permissions'])

    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        if 'kho_vat_tu' in perms:
            perms.pop('kho_vat_tu', None)
            group.module_permissions = perms
            group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0107_trip_menus_under_utilities_admin_only'),
    ]

    operations = [
        migrations.RunPython(add_kho_vat_tu, remove_kho_vat_tu),
    ]
