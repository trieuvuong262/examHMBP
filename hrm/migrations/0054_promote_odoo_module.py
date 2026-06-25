"""Chuyển Odoo từ menu con (audit) sang module/menu cấp cao."""

from django.db import migrations

ODOO_FLAGS = ('view', 'create', 'update', 'delete', 'export')


def _odoo_from_menu(menu_perm: dict | None) -> dict:
    source = menu_perm if isinstance(menu_perm, dict) else {}
    return {flag: bool(source.get(flag, False)) for flag in ODOO_FLAGS}


def promote_odoo_module(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')
    RoleModulePermission = apps.get_model('hrm', 'RoleModulePermission')

    deny = {flag: False for flag in ODOO_FLAGS}

    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        audit = dict(perms.get('audit') or {})
        menus = dict(audit.get('menus') or {})
        odoo_menu = menus.pop('odoo', None)
        if isinstance(odoo_menu, dict):
            perms['odoo'] = _odoo_from_menu(odoo_menu)
        elif 'odoo' not in perms:
            perms['odoo'] = dict(deny)
        if menus != dict(audit.get('menus') or {}):
            audit['menus'] = menus
            perms['audit'] = audit
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])

    for perm in DepartmentMenuPermission.objects.all():
        modules = list(perm.modules or [])
        changed = False
        if 'audit' in modules and 'odoo' not in modules:
            modules.append('odoo')
            changed = True
        if changed:
            perm.modules = modules
            perm.save(update_fields=['modules'])

    role_defaults = {
        'EMPLOYEE': {'view': False, 'edit': False},
        'TEAM_LEADER': {'view': False, 'edit': False},
        'DIVISION_HEAD': {'view': False, 'edit': False},
        'DEPARTMENT_HEAD': {'view': False, 'edit': False},
        'DIRECTOR': {'view': True, 'edit': True},
    }
    for row in RoleModulePermission.objects.all():
        perms = dict(row.module_permissions or {})
        if 'odoo' not in perms:
            perms['odoo'] = role_defaults.get(row.role, {'view': False, 'edit': False})
            row.module_permissions = perms
            row.save(update_fields=['module_permissions'])


def demote_odoo_module(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')
    RoleModulePermission = apps.get_model('hrm', 'RoleModulePermission')

    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        odoo = perms.pop('odoo', None)
        audit = dict(perms.get('audit') or {})
        menus = dict(audit.get('menus') or {})
        if isinstance(odoo, dict):
            menus['odoo'] = {flag: bool(odoo.get(flag, False)) for flag in ODOO_FLAGS}
            audit['menus'] = menus
            perms['audit'] = audit
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])

    for perm in DepartmentMenuPermission.objects.all():
        modules = [m for m in (perm.modules or []) if m != 'odoo']
        perm.modules = modules
        perm.save(update_fields=['modules'])

    for row in RoleModulePermission.objects.all():
        perms = dict(row.module_permissions or {})
        perms.pop('odoo', None)
        row.module_permissions = perms
        row.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0053_sync_odoo_menu_perm'),
    ]

    operations = [
        migrations.RunPython(promote_odoo_module, demote_odoo_module),
    ]
