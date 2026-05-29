from django.db import migrations


def add_audit_module(apps, schema_editor):
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')
    RoleModulePermission = apps.get_model('hrm', 'RoleModulePermission')

    for perm in DepartmentMenuPermission.objects.all():
        modules = list(perm.modules or [])
        if 'audit' not in modules:
            modules.append('audit')
            perm.modules = modules
            perm.save(update_fields=['modules'])

    for row in RoleModulePermission.objects.filter(role='DIRECTOR'):
        perms = dict(row.module_permissions or {})
        perms['audit'] = {'view': True, 'edit': True}
        row.module_permissions = perms
        row.save(update_fields=['module_permissions'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0018_add_permissions_module'),
    ]

    operations = [
        migrations.RunPython(add_audit_module, noop),
    ]
