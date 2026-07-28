from django.db import migrations


def _flags(**kwargs):
    return {
        'view': bool(kwargs.get('view')),
        'create': bool(kwargs.get('create')),
        'update': bool(kwargs.get('update')),
        'delete': bool(kwargs.get('delete')),
        'export': bool(kwargs.get('export')),
    }


def add_kho_san_pham_module(apps, schema_editor):
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')
    RoleModulePermission = apps.get_model('hrm', 'RoleModulePermission')
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')

    for perm in DepartmentMenuPermission.objects.all():
        modules = list(perm.modules or [])
        # Nest under SX stack when SX already enabled
        if 'san_xuat' in modules and 'kho_san_pham' not in modules:
            modules.append('kho_san_pham')
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
        if 'kho_san_pham' not in perms:
            perms['kho_san_pham'] = role_defaults.get(row.role, {'view': True, 'edit': False})
            row.module_permissions = perms
            row.save(update_fields=['module_permissions'])

    view_tpl = _flags(view=True)
    mgr_tpl = _flags(view=True, create=True, update=True, delete=False, export=True)

    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        if 'kho_san_pham' in perms:
            continue
        # Mirror quyền theo kho_npl / san_xuat nếu nhóm đã có stack SX
        has_sx = bool((perms.get('san_xuat') or {}).get('view'))
        has_npl = bool((perms.get('kho_npl') or {}).get('view'))
        if not (has_sx or has_npl):
            continue
        npl = perms.get('kho_npl') or {}
        is_mgr = bool(npl.get('create') or npl.get('update') or (perms.get('san_xuat') or {}).get('create'))
        tpl = mgr_tpl if is_mgr else view_tpl
        perms['kho_san_pham'] = {
            **tpl,
            'menus': {'products': dict(tpl)},
        }
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


def remove_kho_san_pham_module(apps, schema_editor):
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')
    RoleModulePermission = apps.get_model('hrm', 'RoleModulePermission')
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')

    for perm in DepartmentMenuPermission.objects.all():
        modules = [m for m in (perm.modules or []) if m != 'kho_san_pham']
        perm.modules = modules
        perm.save(update_fields=['modules'])

    for row in RoleModulePermission.objects.all():
        perms = dict(row.module_permissions or {})
        perms.pop('kho_san_pham', None)
        row.module_permissions = perms
        row.save(update_fields=['module_permissions'])

    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        perms.pop('kho_san_pham', None)
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0079_seed_reports_general_settings_menu'),
    ]

    operations = [
        migrations.RunPython(add_kho_san_pham_module, remove_kho_san_pham_module),
    ]
