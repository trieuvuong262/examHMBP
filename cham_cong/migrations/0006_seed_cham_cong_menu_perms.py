"""Gắn menu bảng công, nghỉ phép và bảng lương vào nhóm quyền đã lưu.

Nhóm tạo trước các menu này chỉ có chấm công. Quyền xem/tạo lấy theo menu chấm công.
Quyền duyệt lấy theo đơn bổ sung. Ca, địa điểm và báo cáo không bị mở thêm.
"""

from django.db import migrations
import copy


def _flag(row, name):
    if not isinstance(row, dict):
        return False
    if name in row:
        return bool(row[name])
    if name == 'view':
        return bool(row.get('edit'))
    if name in ('create', 'update', 'delete'):
        return bool(row.get('edit'))
    return False


def _perm(*, view, create=False, update=False, delete=False):
    return {
        'view': bool(view or create or update or delete),
        'create': bool(create),
        'update': bool(update),
        'delete': bool(delete),
        'export': False,
        'print': False,
    }


def _fill_menus(menus):
    if not isinstance(menus, dict) or not menus:
        return False
    punch = menus.get('punch') if isinstance(menus.get('punch'), dict) else {}
    supplements = menus.get('supplements') if isinstance(menus.get('supplements'), dict) else {}
    reports = menus.get('hr_reports') if isinstance(menus.get('hr_reports'), dict) else {}
    can_view = _flag(punch, 'view')
    can_create = _flag(punch, 'create')
    can_review = _flag(supplements, 'update')
    can_configure = _flag(reports, 'view') or _flag(reports, 'update')
    wanted = {
        'timesheet': _perm(view=can_view, create=can_create, update=can_review or can_configure),
        'leave': _perm(view=can_view, create=can_create, update=can_review or can_configure),
        'payroll': _perm(view=can_view, create=can_review or can_configure, update=can_configure),
    }
    changed = False
    for key, perm in wanted.items():
        if key in menus:
            continue
        menus[key] = perm
        changed = True
    return changed


def forwards(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        raw = copy.deepcopy(group.module_permissions or {})
        block = raw.get('cham_cong')
        if not isinstance(block, dict):
            continue
        menus = block.get('menus')
        if not _fill_menus(menus):
            continue
        block['menus'] = menus
        raw['cham_cong'] = block
        group.module_permissions = raw
        group.save(update_fields=['module_permissions'])


def backwards(apps, schema_editor):
    PermissionGroup = apps.get_model('hrm', 'PermissionGroup')
    for group in PermissionGroup.objects.all():
        raw = copy.deepcopy(group.module_permissions or {})
        block = raw.get('cham_cong')
        if not isinstance(block, dict) or not isinstance(block.get('menus'), dict):
            continue
        menus = block['menus']
        changed = False
        for key in ('timesheet', 'leave', 'payroll'):
            if key in menus:
                menus.pop(key)
                changed = True
        if not changed:
            continue
        block['menus'] = menus
        raw['cham_cong'] = block
        group.module_permissions = raw
        group.save(update_fields=['module_permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('cham_cong', '0005_payroll'),
        ('hrm', '0120_seed_caro_menu_perm'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
