from django.db import migrations


def _off():
    return {
        'view': False,
        'create': False,
        'update': False,
        'delete': False,
        'export': False,
    }


def migrate_trip_menus_admin_only(apps, schema_editor):
    """Đưa Đặt lịch / Vòng quay vào utilities; tắt quyền nhóm thường (chỉ admin is_staff)."""
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')
    RoleModulePermission = apps.get_model('hrm', 'RoleModulePermission')
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')

    for perm in DepartmentMenuPermission.objects.all():
        modules = [m for m in (perm.modules or []) if m != 'company_trip']
        if modules != list(perm.modules or []):
            perm.modules = modules
            perm.save(update_fields=['modules'])

    for row in RoleModulePermission.objects.all():
        perms = dict(row.module_permissions or {})
        if 'company_trip' in perms:
            perms.pop('company_trip', None)
            row.module_permissions = perms
            row.save(update_fields=['module_permissions'])

    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        changed = False
        if 'company_trip' in perms:
            perms.pop('company_trip', None)
            changed = True
        utilities = dict(perms.get('utilities') or {})
        if utilities:
            menus = dict(utilities.get('menus') or {})
            # Tắt cho mọi nhóm — truy cập qua is_staff ở view/sidebar
            menus['trip_schedule'] = _off()
            menus['lucky_spin'] = _off()
            utilities['menus'] = menus
            perms['utilities'] = utilities
            changed = True
        if changed:
            group.module_permissions = perms
            group.save(update_fields=['module_permissions'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0106_broaden_company_trip_departments'),
    ]

    operations = [
        migrations.RunPython(migrate_trip_menus_admin_only, noop),
    ]
