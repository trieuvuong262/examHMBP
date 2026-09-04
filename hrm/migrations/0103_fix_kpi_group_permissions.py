"""Chuẩn hoá quyền KPI theo nhóm: NV chỉ xem; QL giao/chấm + xem tổng kết."""

from django.db import migrations


def _f(**kwargs):
    flags = {
        'view': bool(kwargs.get('view')),
        'create': bool(kwargs.get('create')),
        'update': bool(kwargs.get('update')),
        'delete': bool(kwargs.get('delete')),
        'export': bool(kwargs.get('export')),
        'print': bool(kwargs.get('print')),
    }
    if any(flags[k] for k in ('create', 'update', 'delete', 'export', 'print')):
        flags['view'] = True
    return flags


VIEW = _f(view=True)
MGR = _f(view=True, create=True, update=True, export=True)
SUMMARY_VIEW = _f(view=True)
SUMMARY_MGR = _f(view=True, export=True)


def _is_kpi_manager_group(slug: str, name: str) -> bool:
    """Phân loại QL theo tên nhóm (slug có thể lệch do copy)."""
    slug_l = (slug or '').casefold()
    name_l = (name or '').casefold()

    if slug_l in {
        'mac-dinh-to-truong',
        'mac-dinh-truong-bo-phan',
        'mac-dinh-giam-doc',
        'it-truong-phong',
        'tgd-truong-phong',
    }:
        return True
    if 'truong-phong' in slug_l or 'to-truong' in slug_l or 'giam-doc' in slug_l:
        return True

    # Tên hiển thị: TP / TT / TGĐ / Trưởng / Giám đốc / IT
    markers = (
        ' - tp',
        '— tp',
        ' tp',
        ' - tt',
        '— tt',
        ' tt',
        'tgđ',
        'tgd',
        'giám đốc',
        'giam doc',
        'tổ trưởng',
        'to truong',
        'trưởng',
        'truong',
    )
    if any(m in name_l for m in markers):
        # Tránh "nhân viên" thuần nếu vô tình khớp
        if name_l.strip() in {'nhân viên', 'nhan vien'}:
            return False
        return True
    if name_l.strip() == 'it':
        return True
    return False


def _kpi_entry(*, manager: bool) -> dict:
    if manager:
        boards = dict(MGR)
        summary = dict(SUMMARY_MGR)
        module = dict(MGR)
    else:
        boards = dict(VIEW)
        summary = dict(SUMMARY_VIEW)
        module = dict(VIEW)
    module['menus'] = {
        'boards': boards,
        'summary': summary,
    }
    return module


def fix_forward(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    RoleModulePermission = apps.get_model('hrm', 'RoleModulePermission')

    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        existing = perms.get('kpi')
        # Giữ nhóm đã tắt KPI hoàn toàn (không có entry / view=False và không menus).
        if isinstance(existing, dict):
            menus = existing.get('menus') if isinstance(existing.get('menus'), dict) else {}
            has_view = bool(existing.get('view')) or any(
                bool((menus.get(k) or {}).get('view')) for k in menus
            )
            if not has_view and existing:
                # Có cấu hình nhưng không xem — giữ nguyên
                continue
        manager = _is_kpi_manager_group(group.slug or '', group.name or '')
        perms['kpi'] = _kpi_entry(manager=manager)
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])

    role_mgr = {
        'EMPLOYEE': False,
        'TEAM_LEADER': True,
        'DIVISION_HEAD': True,
        'DEPARTMENT_HEAD': True,
        'DIRECTOR': True,
    }
    for row in RoleModulePermission.objects.all():
        perms = dict(row.module_permissions or {})
        is_mgr = role_mgr.get(row.role, False)
        # RoleModulePermission dùng legacy view/edit
        perms['kpi'] = {'view': True, 'edit': bool(is_mgr)}
        row.module_permissions = perms
        row.save(update_fields=['module_permissions'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0102_seed_kpi_submenus'),
    ]

    operations = [
        migrations.RunPython(fix_forward, noop_reverse),
    ]
