"""Khôi phục module KPI vào phân quyền phòng ban / nhóm sau khi bật lại portal."""

from django.db import migrations


def _flags(**kwargs):
    return {
        'view': bool(kwargs.get('view')),
        'create': bool(kwargs.get('create')),
        'update': bool(kwargs.get('update')),
        'delete': bool(kwargs.get('delete')),
        'export': bool(kwargs.get('export')),
        'print': bool(kwargs.get('print')),
    }


def restore_kpi(apps, schema_editor):
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    RoleModulePermission = apps.get_model('hrm', 'RoleModulePermission')

    for perm in DepartmentMenuPermission.objects.all():
        modules = list(perm.modules or [])
        if not modules:
            # Rỗng = full quyền — không cần ghi kpi.
            continue
        if 'kpi' not in modules:
            modules.append('kpi')
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
        entry = perms.get('kpi')
        if not isinstance(entry, dict) or not entry.get('view'):
            perms['kpi'] = role_defaults.get(row.role, {'view': True, 'edit': False})
            row.module_permissions = perms
            row.save(update_fields=['module_permissions'])

    view_tpl = _flags(view=True)
    mgr_tpl = _flags(view=True, create=True, update=True, delete=False, export=True)

    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        existing = perms.get('kpi')
        if isinstance(existing, dict) and existing.get('view'):
            continue
        # Nhóm quản lý: có create/update trên reports hoặc hrm → KPI mức quản lý.
        is_mgr = any(
            bool((perms.get(key) or {}).get(action))
            for key in ('reports', 'hrm', 'permissions', 'audit')
            for action in ('create', 'update', 'edit')
        ) or 'truong' in (group.slug or '') or 'to-truong' in (group.slug or '')
        perms['kpi'] = dict(mgr_tpl if is_mgr else view_tpl)
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


def noop_reverse(apps, schema_editor):
    # Không gỡ KPI khi reverse — tránh mất quyền đã cấu hình tay.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0100_seed_kho_sp_receipts_menu'),
    ]

    operations = [
        migrations.RunPython(restore_kpi, noop_reverse),
    ]
