from django.db import migrations


def add_tasks_module(apps, schema_editor):
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')
    RoleModulePermission = apps.get_model('hrm', 'RoleModulePermission')

    for perm in DepartmentMenuPermission.objects.all():
        modules = list(perm.modules or [])
        if 'tasks' not in modules:
            modules.append('tasks')
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
        if 'tasks' not in perms:
            perms['tasks'] = role_defaults.get(row.role, {'view': True, 'edit': False})
            row.module_permissions = perms
            row.save(update_fields=['module_permissions'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0019_add_audit_module'),
    ]

    operations = [
        migrations.RunPython(add_tasks_module, noop),
    ]
