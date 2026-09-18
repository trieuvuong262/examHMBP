from django.db import migrations


def _flags(**kwargs):
    return {
        'view': bool(kwargs.get('view')),
        'create': bool(kwargs.get('create')),
        'update': bool(kwargs.get('update')),
        'delete': bool(kwargs.get('delete')),
        'export': bool(kwargs.get('export')),
    }


def add_company_trip_module(apps, schema_editor):
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')
    RoleModulePermission = apps.get_model('hrm', 'RoleModulePermission')
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')

    # Mọi phòng ban đã có utilities/surveys/feedback → thêm company_trip
    for perm in DepartmentMenuPermission.objects.all():
        modules = list(perm.modules or [])
        if 'company_trip' in modules:
            continue
        if any(m in modules for m in ('utilities', 'surveys', 'feedback', 'announcements')):
            modules.append('company_trip')
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
        if 'company_trip' not in perms:
            perms['company_trip'] = role_defaults.get(row.role, {'view': True, 'edit': False})
            row.module_permissions = perms
            row.save(update_fields=['module_permissions'])

    emp_tpl = _flags(view=True, create=True)
    mgr_tpl = _flags(view=True, create=True, update=True, delete=True, export=True)

    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        if 'company_trip' in perms:
            continue
        # Cấp cho mọi nhóm đã có ít nhất 1 module portal (để NV đăng ký được)
        if not perms:
            continue
        util = perms.get('utilities') or {}
        surveys = perms.get('surveys') or {}
        hrm = perms.get('hrm') or {}
        is_mgr = bool(
            util.get('create') or util.get('update')
            or surveys.get('create') or surveys.get('update')
            or hrm.get('create') or hrm.get('update')
        )
        base = mgr_tpl if is_mgr else emp_tpl
        menus = {
            'register': dict(emp_tpl),
        }
        if is_mgr:
            menus.update({
                'manage_regs': dict(mgr_tpl),
                'rooms': dict(mgr_tpl),
                'email': dict(mgr_tpl),
                'spin': dict(mgr_tpl),
            })
        else:
            # NV chỉ đăng ký
            menus.update({
                'manage_regs': _flags(),
                'rooms': _flags(),
                'email': _flags(),
                'spin': _flags(),
            })
        perms['company_trip'] = {**base, 'menus': menus}
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


def remove_company_trip_module(apps, schema_editor):
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')
    RoleModulePermission = apps.get_model('hrm', 'RoleModulePermission')
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')

    for perm in DepartmentMenuPermission.objects.all():
        modules = [m for m in (perm.modules or []) if m != 'company_trip']
        perm.modules = modules
        perm.save(update_fields=['modules'])

    for row in RoleModulePermission.objects.all():
        perms = dict(row.module_permissions or {})
        perms.pop('company_trip', None)
        row.module_permissions = perms
        row.save(update_fields=['module_permissions'])

    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        perms.pop('company_trip', None)
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0104_grant_it_san_xuat_writes'),
    ]

    operations = [
        migrations.RunPython(add_company_trip_module, remove_company_trip_module),
    ]
