"""
Nhóm quyền — 5 hành động / module: xem, thêm, sửa, xoá, xuất Excel.

Profile.permission_group là nguồn chính; fallback RoleModulePermission theo vai trò (tương thích cũ).
"""

from hrm.module_permissions import ALL_MODULE_KEYS, MODULE_CHOICES, MODULE_LABELS
from hrm.permissions import ROLE_EMPLOYEE, get_profile, user_role

PERM_VIEW = 'view'
PERM_CREATE = 'create'
PERM_UPDATE = 'update'
PERM_DELETE = 'delete'
PERM_EXPORT = 'export'

PERM_ACTIONS = (PERM_VIEW, PERM_CREATE, PERM_UPDATE, PERM_DELETE, PERM_EXPORT)

PERM_ACTION_LABELS = {
    PERM_VIEW: 'Xem',
    PERM_CREATE: 'Thêm',
    PERM_UPDATE: 'Sửa',
    PERM_DELETE: 'Xóa',
    PERM_EXPORT: 'Xuất Excel',
}

DEFAULT_GROUP_SLUGS = {
    'EMPLOYEE': 'mac-dinh-nhan-vien',
    'TEAM_LEADER': 'mac-dinh-to-truong',
    'DIVISION_HEAD': 'mac-dinh-truong-bo-phan',
    'DIRECTOR': 'mac-dinh-giam-doc',
}


def empty_module_perm() -> dict:
    return {action: False for action in PERM_ACTIONS}


def legacy_entry_to_five_flags(entry) -> dict:
    """Chuyển {view, edit} cũ → 5 quyền."""
    if not isinstance(entry, dict):
        return empty_module_perm()

    granular_keys = (PERM_CREATE, PERM_UPDATE, PERM_DELETE, PERM_EXPORT)
    if any(action in entry for action in granular_keys):
        return normalize_module_perm(entry)

    view = bool(entry.get('view', False))
    edit = bool(entry.get('edit', False))
    if edit:
        view = True
    return {
        PERM_VIEW: view,
        PERM_CREATE: edit,
        PERM_UPDATE: edit,
        PERM_DELETE: edit,
        PERM_EXPORT: edit,
    }


def normalize_module_perm(raw: dict | None) -> dict:
    source = raw or {}
    result = empty_module_perm()
    for action in PERM_ACTIONS:
        result[action] = bool(source.get(action, False))
    if any(result[a] for a in (PERM_CREATE, PERM_UPDATE, PERM_DELETE, PERM_EXPORT)):
        result[PERM_VIEW] = True
    return result


def normalize_group_permissions(raw: dict | None) -> dict:
    from hrm.role_permissions import default_role_permissions

    base = default_role_permissions().get(ROLE_EMPLOYEE, {})
    source = raw or {}
    result = {}
    for module_key in ALL_MODULE_KEYS:
        entry = source.get(module_key, base.get(module_key))
        if isinstance(entry, bool):
            entry = {'view': entry, 'edit': entry}
        elif entry is None:
            entry = {}
        result[module_key] = legacy_entry_to_five_flags(entry)
    return result


def permissions_from_legacy_role(role: str) -> dict:
    from hrm.role_permissions import get_role_permissions

    legacy = get_role_permissions(role)
    return {
        module_key: legacy_entry_to_five_flags(entry)
        for module_key, entry in legacy.items()
    }


def get_user_group_permissions(user) -> dict:
    """Ma trận quyền hiệu lực của user — {module: {view, create, ...}}."""
    from hrm.module_permissions import bypass_department_modules

    if bypass_department_modules(user):
        full = empty_module_perm()
        full.update({a: True for a in PERM_ACTIONS})
        return {key: dict(full) for key in ALL_MODULE_KEYS}

    profile = get_profile(user)
    if profile and profile.permission_group_id:
        return profile.permission_group.get_permissions()

    return permissions_from_legacy_role(user_role(user))


def get_user_module_perm(user, module_key: str) -> dict:
    if module_key not in ALL_MODULE_KEYS:
        full = empty_module_perm()
        full.update({a: True for a in PERM_ACTIONS})
        return full
    return get_user_group_permissions(user).get(module_key, empty_module_perm())


def module_perm_allows_view(perm: dict) -> bool:
    return bool(perm.get(PERM_VIEW))


def module_perm_allows_edit(perm: dict) -> bool:
    return any(perm.get(a) for a in (PERM_CREATE, PERM_UPDATE, PERM_DELETE))


def group_permission_summary(permissions: dict) -> list:
    rows = []
    for key, label in MODULE_CHOICES:
        perm = permissions.get(key, empty_module_perm())
        actions = [PERM_ACTION_LABELS[a] for a in PERM_ACTIONS if perm.get(a)]
        if not actions:
            level = 'Không truy cập'
        elif perm.get(PERM_VIEW) and not module_perm_allows_edit(perm) and not perm.get(PERM_EXPORT):
            level = 'Chỉ xem'
        else:
            level = ', '.join(actions)
        rows.append({
            'key': key,
            'label': label,
            'perm': perm,
            'level': level,
            'actions': actions,
        })
    return rows


def default_group_for_role(role: str):
    from hrm.models import PermissionGroup

    slug = DEFAULT_GROUP_SLUGS.get(role)
    if not slug:
        return None
    return PermissionGroup.objects.filter(slug=slug).first()
