from django.db import migrations


def add_san_xuat_module(apps, schema_editor):
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')
    RoleModulePermission = apps.get_model('hrm', 'RoleModulePermission')
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')

    for perm in DepartmentMenuPermission.objects.all():
        modules = list(perm.modules or [])
        if 'san_xuat' not in modules:
            modules.append('san_xuat')
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
        if 'san_xuat' not in perms:
            perms['san_xuat'] = role_defaults.get(row.role, {'view': True, 'edit': False})
            row.module_permissions = perms
            row.save(update_fields=['module_permissions'])

    san_xuat_perm = {
        'view': True,
        'create': False,
        'update': False,
        'delete': False,
        'export': False,
    }
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        if 'san_xuat' not in perms:
            perms['san_xuat'] = dict(san_xuat_perm)
            group.module_permissions = perms
            group.save(update_fields=['module_permissions'])


def remove_san_xuat_module(apps, schema_editor):
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')
    RoleModulePermission = apps.get_model('hrm', 'RoleModulePermission')
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')

    for perm in DepartmentMenuPermission.objects.all():
        modules = [m for m in (perm.modules or []) if m != 'san_xuat']
        perm.modules = modules
        perm.save(update_fields=['modules'])

    for row in RoleModulePermission.objects.all():
        perms = dict(row.module_permissions or {})
        perms.pop('san_xuat', None)
        row.module_permissions = perms
        row.save(update_fields=['module_permissions'])

    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        perms.pop('san_xuat', None)
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0060_alter_profile_on_probation'),
    ]

    operations = [
        migrations.RunPython(add_san_xuat_module, remove_san_xuat_module),
    ]
