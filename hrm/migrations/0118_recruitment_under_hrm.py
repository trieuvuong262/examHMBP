"""Bật lại Tuyển dụng trong nhóm Nhân sự — cấp quyền menu cho dữ liệu cũ.

Module Tuyển dụng từng bị ẩn nên form phân quyền không lưu key ``recruitment``:
- Phòng ban có giới hạn module (list không rỗng) thiếu ``recruitment``.
- Nhóm quyền thiếu ``recruitment`` → mặc định không có quyền.

Migration này:
- Thêm ``recruitment`` cho phòng ban đang có ``hrm``.
- Nhóm quyền chưa có quyền Tuyển dụng → sao chép quyền từ menu
  «Danh sách nhân viên» (hrm.users) sang 2 menu con Ứng viên / Vị trí tuyển dụng.
"""

from django.db import migrations

ACTIONS = ('view', 'create', 'update', 'delete', 'export', 'print')


def _flags(source: dict, *, allow_export: bool) -> dict:
    entry = {action: bool(source.get(action)) for action in ACTIONS}
    entry['print'] = False
    if not allow_export:
        entry['export'] = False
    if any(entry[a] for a in ('create', 'update', 'delete', 'export')):
        entry['view'] = True
    return entry


def _has_any(entry) -> bool:
    if not isinstance(entry, dict):
        return False
    if any(entry.get(a) for a in ACTIONS):
        return True
    menus = entry.get('menus')
    return isinstance(menus, dict) and any(
        isinstance(m, dict) and any(m.get(a) for a in ACTIONS) for m in menus.values()
    )


def forward(apps, schema_editor):
    DepartmentMenuPermission = apps.get_model('hrm', 'DepartmentMenuPermission')
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')

    for perm in DepartmentMenuPermission.objects.all():
        modules = list(perm.modules or [])
        if not modules:
            continue  # Rỗng = full quyền.
        if 'hrm' in modules and 'recruitment' not in modules:
            modules.append('recruitment')
            perm.modules = modules
            perm.save(update_fields=['modules'])

    for group in PermissionGroup.objects.all():
        perms = dict(group.module_permissions or {})
        if _has_any(perms.get('recruitment')):
            continue
        hrm = perms.get('hrm') or {}
        if not isinstance(hrm, dict):
            continue
        hrm_menus = hrm.get('menus') if isinstance(hrm.get('menus'), dict) else {}
        source = hrm_menus.get('users') if hrm_menus else hrm
        if not isinstance(source, dict) or not any(source.get(a) for a in ACTIONS):
            continue
        menus = {
            'candidates': _flags(source, allow_export=True),
            'jobs': _flags(source, allow_export=False),
        }
        entry = {
            action: any(m.get(action) for m in menus.values()) for action in ACTIONS
        }
        entry['menus'] = menus
        perms['recruitment'] = entry
        group.module_permissions = perms
        group.save(update_fields=['module_permissions'])


def noop_reverse(apps, schema_editor):
    # Không gỡ quyền khi reverse — tránh mất cấu hình đã chỉnh tay.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('hrm', '0117_it_price_menus'),
    ]

    operations = [
        migrations.RunPython(forward, noop_reverse),
    ]
