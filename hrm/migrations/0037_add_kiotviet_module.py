from django.db import migrations


def add_kiotviet_module(apps, schema_editor):
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')
    RoleModulePermission = apps.get_model('hrm', 'RoleModulePermission')
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')

    for perm in DepartmentMenuPermission.objects.all():
        modules = list(perm.modules or [])
        if 'kiotviet' not in modules:
            modules.append('kiotviet')
            perm.modules = modules
            perm.save(update_fields=['modules'])

    role_defaults = {
        'EMPLOYEE': {'view': True, 'edit': False},
        'TEAM_LEADER': {'view': True, 'edit': True},
        'DIVISION_HEAD': {'view': True, 'edit': True},
        'DIRECTOR': {'view': True, 'edit': True},
    }
    for row in RoleModulePermission.objects.all():
        perms = dict(row.module_permissions or {})
        if 'kiotviet' not in perms:
            perms['kiotviet'] = role_defaults.get(row.role, {'view': True, 'edit': False})
            row.module_permissions = perms
            row.save(update_fields=['module_permissions'])

    kiotviet_perm = {
        'view': True,
        'create': False,
        'update': False,
        'delete': False,
        'export': False,
    }
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        if 'kiotviet' not in perms:
            perms['kiotviet'] = dict(kiotviet_perm)
            group.module_permissions = perms
            group.save(update_fields=['module_permissions'])


def remove_kiotviet_module(apps, schema_editor):
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')
    RoleModulePermission = apps.get_model('hrm', 'RoleModulePermission')
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')

    for perm in DepartmentMenuPermission.objects.all():
        modules = [m for m in (perm.modules or []) if m != 'kiotviet']
        perm.modules = modules
        perm.save(update_fields=['modules'])

    for row in RoleModulePermission.objects.all():
        perms = dict(row.module_permissions or {})
        perms.pop('kiotviet', None)
        row.module_permissions = perms
        row.save(update_fields=['module_permissions'])

    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        perms.pop('kiotviet', None)
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0036_report_profile_routing'),
    ]

    operations = [
        migrations.RunPython(add_kiotviet_module, remove_kiotviet_module),
    ]
