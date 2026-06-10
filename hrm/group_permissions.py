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

# Module có chức năng tải/xuất file Excel thực tế — các module khác ẩn cột Excel trong ma trận phân quyền.
MODULE_SUPPORTS_EXPORT = frozenset({
    'hrm',          # Xuất danh sách nhân viên
    'recruitment',  # Xuất lịch PV, giấy phép
    'equipment',    # Xuất danh sách thiết bị
    'audit',        # Xuất nhật ký thao tác
    'kho_npl',      # Báo cáo tồn kho / sổ kho
})

# Module chỉ dùng quyền Xem + Xuất Excel (ẩn Thêm/Sửa/Xóa trong ma trận phân quyền).
MODULE_VIEW_EXPORT_ONLY = frozenset({
    'audit',
})


def module_supports_export(module_key: str) -> bool:
    return module_key in MODULE_SUPPORTS_EXPORT


def module_permission_action_enabled(module_key: str, action: str) -> bool:
    if module_key in MODULE_VIEW_EXPORT_ONLY:
        return action in (PERM_VIEW, PERM_EXPORT)
    if action == PERM_EXPORT:
        return module_supports_export(module_key)
    return True

DEFAULT_GROUP_SLUGS = {
    'EMPLOYEE': 'mac-dinh-nhan-vien',
    'TEAM_LEADER': 'mac-dinh-to-truong',
    'DIVISION_HEAD': 'mac-dinh-truong-bo-phan',
    'DEPARTMENT_HEAD': 'mac-dinh-truong-phong',
    'DIRECTOR': 'mac-dinh-giam-doc',
}


def empty_module_perm() -> dict:
    return {action: False for action in PERM_ACTIONS}


def legacy_entry_to_five_flags(entry, *, module_key: str | None = None) -> dict:
    """Chuyển {view, edit} cũ → 5 quyền."""
    if not isinstance(entry, dict):
        return empty_module_perm()

    granular_keys = (PERM_CREATE, PERM_UPDATE, PERM_DELETE, PERM_EXPORT)
    if any(action in entry for action in granular_keys):
        return normalize_module_perm(entry, module_key=module_key)

    view = bool(entry.get('view', False))
    edit = bool(entry.get('edit', False))
    if edit:
        view = True
    if module_key in MODULE_VIEW_EXPORT_ONLY:
        return {
            PERM_VIEW: view,
            PERM_CREATE: False,
            PERM_UPDATE: False,
            PERM_DELETE: False,
            PERM_EXPORT: edit,
        }
    return {
        PERM_VIEW: view,
        PERM_CREATE: edit,
        PERM_UPDATE: edit,
        PERM_DELETE: edit,
        PERM_EXPORT: edit if module_supports_export(module_key or '') else False,
    }


def normalize_module_perm(raw: dict | None, *, module_key: str | None = None) -> dict:
    source = raw or {}
    result = empty_module_perm()
    for action in PERM_ACTIONS:
        result[action] = bool(source.get(action, False))
    if module_key and not module_supports_export(module_key):
        result[PERM_EXPORT] = False
    if module_key in MODULE_VIEW_EXPORT_ONLY:
        result[PERM_CREATE] = False
        result[PERM_UPDATE] = False
        result[PERM_DELETE] = False
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
        result[module_key] = normalize_module_perm(
            legacy_entry_to_five_flags(entry, module_key=module_key),
            module_key=module_key,
        )
    return result


def permissions_from_legacy_role(role: str) -> dict:
    from hrm.role_permissions import get_role_permissions

    legacy = get_role_permissions(role)
    return {
        module_key: normalize_module_perm(
            legacy_entry_to_five_flags(entry, module_key=module_key),
            module_key=module_key,
        )
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


MODULE_LIST_META = {
    'announcements': {'icon': 'bi-megaphone', 'short': 'TB'},
    'recruitment': {'icon': 'bi-person-plus', 'short': 'TD'},
    'training': {'icon': 'bi-mortarboard', 'short': 'ĐT'},
    'assessment': {'icon': 'bi-patch-check', 'short': 'KT'},
    'hrm': {'icon': 'bi-people', 'short': 'NS'},
    'kpi': {'icon': 'bi-graph-up-arrow', 'short': 'KPI'},
    'reports': {'icon': 'bi-journal-text', 'short': 'BC'},
    'guide': {'icon': 'bi-book', 'short': 'HD'},
    'documents': {'icon': 'bi-folder2', 'short': 'TV'},
    'permissions': {'icon': 'bi-shield-lock', 'short': 'PQ'},
    'audit': {'icon': 'bi-clock-history', 'short': 'NK'},
    'tasks': {'icon': 'bi-kanban', 'short': 'CV'},
    'de_xuat': {'icon': 'bi-lightbulb', 'short': 'ĐX'},
    'ho_tro': {'icon': 'bi-tools', 'short': 'HT'},
    'nas_storage': {'icon': 'bi-hdd-network', 'short': 'NAS'},
    'equipment': {'icon': 'bi-pc-display', 'short': 'TB'},
    'feedback': {'icon': 'bi-chat-square-text', 'short': 'GY'},
    'kiotviet': {'icon': 'bi-shop', 'short': 'KV'},
    'kho_npl': {'icon': 'bi-boxes', 'short': 'NPL'},
}


def _module_perm_tier(perm: dict) -> str:
    if not perm.get(PERM_VIEW):
        return 'none'
    if all(perm.get(a) for a in PERM_ACTIONS):
        return 'full'
    if not module_perm_allows_edit(perm) and not perm.get(PERM_EXPORT):
        return 'view'
    return 'partial'


def group_list_summary(permissions: dict) -> dict:
    """Tóm tắt gọn cho danh sách nhóm quyền."""
    modules = []
    view_count = partial_count = full_count = 0
    for key, label in MODULE_CHOICES:
        perm = permissions.get(key, empty_module_perm())
        tier = _module_perm_tier(perm)
        if tier == 'none':
            continue
        meta = MODULE_LIST_META.get(key, {'icon': 'bi-grid', 'short': label[:3]})
        actions = [PERM_ACTION_LABELS[a] for a in PERM_ACTIONS if perm.get(a)]
        if tier == 'view':
            view_count += 1
            level_text = 'Chỉ xem'
        elif tier == 'full':
            full_count += 1
            level_text = 'Đủ 5 quyền'
        else:
            partial_count += 1
            level_text = ', '.join(actions)
        modules.append({
            'key': key,
            'label': label,
            'short': meta['short'],
            'icon': meta['icon'],
            'tier': tier,
            'level_text': level_text,
        })
    return {
        'modules': modules,
        'active_count': len(modules),
        'total_count': len(MODULE_CHOICES),
        'view_count': view_count,
        'partial_count': partial_count,
        'full_count': full_count,
    }


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
