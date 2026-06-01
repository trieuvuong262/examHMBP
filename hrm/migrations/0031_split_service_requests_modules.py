from django.db import migrations


def _split_module_list(modules):
    result = list(modules or [])
    if 'service_requests' not in result:
        return result, False
    result = [m for m in result if m != 'service_requests']
    for key in ('de_xuat', 'ho_tro'):
        if key not in result:
            result.append(key)
    return result, True


def _split_module_permissions(perms):
    source = dict(perms or {})
    if 'service_requests' not in source:
        return source, False
    legacy = source.pop('service_requests')
    source.setdefault('de_xuat', legacy)
    source.setdefault('ho_tro', legacy)
    return source, True


def split_service_requests_modules(apps, schema_editor):
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')
    RoleModulePermission = apps.get_model('hrm', 'RoleModulePermission')
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')

    for perm in DepartmentMenuPermission.objects.all():
        modules, changed = _split_module_list(perm.modules)
        if changed:
            perm.modules = modules
            perm.save(update_fields=['modules'])

    for row in RoleModulePermission.objects.all():
        perms, changed = _split_module_permissions(row.module_permissions)
        if changed:
            row.module_permissions = perms
            row.save(update_fields=['module_permissions'])

    for group in PermissionGroup.objects.all():
        perms, changed = _split_module_permissions(group.module_permissions)
        if changed:
            group.module_permissions = perms
            group.save(update_fields=['module_permissions'])


def merge_service_requests_modules(apps, schema_editor):
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')
    RoleModulePermission = apps.get_model('hrm', 'RoleModulePermission')
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')

    for perm in DepartmentMenuPermission.objects.all():
        modules = list(perm.modules or [])
        if 'de_xuat' in modules or 'ho_tro' in modules:
            modules = [m for m in modules if m not in ('de_xuat', 'ho_tro')]
            if 'service_requests' not in modules:
                modules.append('service_requests')
            perm.modules = modules
            perm.save(update_fields=['modules'])

    for row in RoleModulePermission.objects.all():
        perms = dict(row.module_permissions or {})
        if 'de_xuat' in perms or 'ho_tro' in perms:
            legacy = perms.get('de_xuat') or perms.get('ho_tro') or {'view': True, 'edit': False}
            perms.pop('de_xuat', None)
            perms.pop('ho_tro', None)
            perms['service_requests'] = legacy
            row.module_permissions = perms
            row.save(update_fields=['module_permissions'])

    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        if 'de_xuat' in perms or 'ho_tro' in perms:
            legacy = perms.get('de_xuat') or perms.get('ho_tro') or {}
            perms.pop('de_xuat', None)
            perms.pop('ho_tro', None)
            perms['service_requests'] = legacy
            group.module_permissions = perms
            group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0030_add_feedback_module'),
    ]

    operations = [
        migrations.RunPython(split_service_requests_modules, merge_service_requests_modules),
    ]
