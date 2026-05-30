"""
Phân quyền theo nhóm quyền (PermissionGroup) hoặc fallback vai trò hệ thống.

Vai trò (Profile.role) vẫn dùng cho cấu trúc tổ chức — giao việc, báo cáo, v.v.
"""

from hrm.module_permissions import (
    ALL_MODULE_KEYS,
    MODULE_AUDIT,
    MODULE_ANNOUNCEMENTS,
    MODULE_ASSESSMENT,
    MODULE_DOCUMENTS,
    MODULE_GUIDE,
    MODULE_HRM,
    MODULE_KPI,
    MODULE_PERMISSIONS,
    MODULE_RECRUITMENT,
    MODULE_REPORTS,
    MODULE_TASKS,
    MODULE_SERVICE_REQUESTS,
    MODULE_NAS_STORAGE,
    MODULE_TRAINING,
    bypass_department_modules,
)
from hrm.permissions import (
    ROLE_CHOICES,
    ROLE_DIRECTOR,
    ROLE_DIVISION_HEAD,
    ROLE_EMPLOYEE,
    ROLE_TEAM_LEADER,
    user_role,
)


def _perm(view=False, edit=False):
    return {'view': bool(view), 'edit': bool(edit)}


def default_role_permissions() -> dict:
    """Mặc định khi chưa cấu hình — dùng khi seed / fallback."""
    employee_modules = {
        MODULE_ANNOUNCEMENTS: _perm(True, False),
        MODULE_TRAINING: _perm(True, False),
        MODULE_ASSESSMENT: _perm(True, False),
        MODULE_KPI: _perm(True, False),
        MODULE_REPORTS: _perm(True, False),
        MODULE_GUIDE: _perm(True, False),
        MODULE_DOCUMENTS: _perm(True, False),
        MODULE_TASKS: _perm(True, False),
        MODULE_SERVICE_REQUESTS: _perm(True, False),
        MODULE_NAS_STORAGE: _perm(True, True),
        MODULE_PERMISSIONS: _perm(False, False),
        MODULE_AUDIT: _perm(False, False),
        MODULE_RECRUITMENT: _perm(False, False),
        MODULE_HRM: _perm(False, False),
    }
    manager_extra = {
        MODULE_REPORTS: _perm(True, True),
        MODULE_KPI: _perm(True, True),
        MODULE_GUIDE: _perm(True, True),
        MODULE_TASKS: _perm(True, True),
        MODULE_SERVICE_REQUESTS: _perm(True, True),
    }
    team_leader = {**employee_modules, **manager_extra}
    division_head = {
        **team_leader,
        MODULE_TRAINING: _perm(True, True),
        MODULE_ASSESSMENT: _perm(True, True),
    }
    director = {key: _perm(True, True) for key in ALL_MODULE_KEYS}
    return {
        ROLE_EMPLOYEE: employee_modules,
        ROLE_TEAM_LEADER: team_leader,
        ROLE_DIVISION_HEAD: division_head,
        ROLE_DIRECTOR: director,
    }


def normalize_module_permissions(raw: dict | None) -> dict:
    """Chuẩn hóa JSON legacy {view, edit}."""
    defaults = default_role_permissions()
    base = defaults.get(ROLE_EMPLOYEE, {})
    result = {}
    source = raw or {}
    for module_key in ALL_MODULE_KEYS:
        entry = source.get(module_key, base.get(module_key, _perm(False, False)))
        if isinstance(entry, bool):
            entry = _perm(entry, entry)
        view = bool(entry.get('view', False))
        edit = bool(entry.get('edit', False))
        if edit:
            view = True
        result[module_key] = {'view': view, 'edit': edit}
    return result


def get_role_permissions(role: str) -> dict:
    from django.db.utils import OperationalError, ProgrammingError
    from hrm.models import RoleModulePermission

    defaults = default_role_permissions()
    fallback = defaults.get(role, defaults[ROLE_EMPLOYEE])
    try:
        row = RoleModulePermission.objects.get(role=role)
        stored = normalize_module_permissions(row.module_permissions)
    except RoleModulePermission.DoesNotExist:
        stored = normalize_module_permissions(fallback)
    except (ProgrammingError, OperationalError):
        stored = normalize_module_permissions(fallback)

    merged = {}
    for module_key in ALL_MODULE_KEYS:
        merged[module_key] = stored.get(
            module_key,
            fallback.get(module_key, _perm(False, False)),
        )
    return merged


def get_user_module_permission(user, module_key: str) -> dict:
    from hrm.group_permissions import get_user_module_perm
    return get_user_module_perm(user, module_key)


def role_allows_view(user, module_key: str) -> bool:
    if module_key not in ALL_MODULE_KEYS:
        return True
    if bypass_department_modules(user):
        return True
    from hrm.group_permissions import module_perm_allows_view
    return module_perm_allows_view(get_user_module_permission(user, module_key))


def role_allows_edit(user, module_key: str) -> bool:
    if module_key not in ALL_MODULE_KEYS:
        return True
    if bypass_department_modules(user):
        return True
    from hrm.group_permissions import module_perm_allows_edit
    return module_perm_allows_edit(get_user_module_permission(user, module_key))


def user_can_edit_module(user, module_key: str) -> bool:
    return role_allows_edit(user, module_key)


def user_can_view_module(user, module_key: str) -> bool:
    return role_allows_view(user, module_key)


def role_permission_summary(role: str) -> list:
    from hrm.group_permissions import group_permission_summary, permissions_from_legacy_role
    return group_permission_summary(permissions_from_legacy_role(role))


ROLE_LABELS = dict(ROLE_CHOICES)
