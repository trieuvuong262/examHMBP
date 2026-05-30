from django.db import migrations


def add_nas_storage_module(apps, schema_editor):
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')
    RoleModulePermission = apps.get_model('hrm', 'RoleModulePermission')
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')

    for perm in DepartmentMenuPermission.objects.all():
        modules = list(perm.modules or [])
        if 'nas_storage' not in modules:
            modules.append('nas_storage')
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
        if 'nas_storage' not in perms:
            perms['nas_storage'] = role_defaults.get(row.role, {'view': True, 'edit': False})
            row.module_permissions = perms
            row.save(update_fields=['module_permissions'])

    nas_perm = {'view': True, 'create': False, 'update': False, 'delete': False, 'export': False}
    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        if 'nas_storage' not in perms:
            perms['nas_storage'] = dict(nas_perm)
            group.module_permissions = perms
            group.save(update_fields=['module_permissions'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0026_sample_groups_are_templates'),
    ]

    operations = [
        migrations.RunPython(add_nas_storage_module, noop),
    ]
