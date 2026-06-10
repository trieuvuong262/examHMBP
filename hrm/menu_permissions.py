"""
Phân quyền menu con — kiểm tra quyền theo từng submenu trong nhóm quyền.
"""

from hrm.group_permissions import (
    PERM_ACTIONS,
    PERM_CREATE,
    PERM_DELETE,
    PERM_EXPORT,
    PERM_UPDATE,
    PERM_VIEW,
    empty_module_perm,
    get_user_module_perm,
    module_perm_allows_edit,
    module_perm_allows_view,
)
from hrm.module_permissions import (
    MODULE_LABELS,
    bypass_department_modules,
    get_user_enabled_modules,
)
from hrm.submenu_registry import (
    MENU_PATH_RULES,
    get_menu_label,
    get_module_submenus,
    module_has_submenus,
)

_MENU_ACTION_CHECKS = {
    PERM_VIEW: lambda perm: module_perm_allows_view(perm),
    PERM_CREATE: lambda perm: bool(perm.get(PERM_CREATE)),
    PERM_UPDATE: lambda perm: bool(perm.get(PERM_UPDATE)),
    PERM_DELETE: lambda perm: bool(perm.get(PERM_DELETE)),
    PERM_EXPORT: lambda perm: bool(perm.get(PERM_EXPORT)),
    'edit': lambda perm: module_perm_allows_edit(perm),
}


def module_has_configured_menus(perm: dict) -> bool:
    menus = perm.get('menus')
    return isinstance(menus, dict) and bool(menus)


def get_effective_menu_perm(user, module_key: str, menu_key: str) -> dict:
    """Quyền hiệu lực của một menu con — kế thừa module nếu chưa cấu hình menus."""
    mod_perm = get_user_module_perm(user, module_key)
    menus = mod_perm.get('menus')
    if not isinstance(menus, dict) or menu_key not in menus:
        return {action: bool(mod_perm.get(action)) for action in PERM_ACTIONS}
    menu_perm = menus[menu_key]
    return {action: bool(menu_perm.get(action)) for action in PERM_ACTIONS}


def user_can_menu_action(user, module_key: str, menu_key: str, action: str) -> bool:
    if not getattr(user, 'is_authenticated', False):
        return False
    if bypass_department_modules(user):
        return True
    if module_key not in get_user_enabled_modules(user):
        return False
    perm = get_effective_menu_perm(user, module_key, menu_key)
    checker = _MENU_ACTION_CHECKS.get(action, _MENU_ACTION_CHECKS['edit'])
    return bool(checker(perm))


def user_can_access_menu(user, module_key: str, menu_key: str) -> bool:
    return user_can_menu_action(user, module_key, menu_key, PERM_VIEW)


def user_can_create_menu(user, module_key: str, menu_key: str) -> bool:
    return user_can_menu_action(user, module_key, menu_key, PERM_CREATE)


def user_can_update_menu(user, module_key: str, menu_key: str) -> bool:
    return user_can_menu_action(user, module_key, menu_key, PERM_UPDATE)


def user_can_delete_menu(user, module_key: str, menu_key: str) -> bool:
    return user_can_menu_action(user, module_key, menu_key, PERM_DELETE)


def user_can_export_menu(user, module_key: str, menu_key: str) -> bool:
    return user_can_menu_action(user, module_key, menu_key, PERM_EXPORT)


def user_can_edit_menu(user, module_key: str, menu_key: str) -> bool:
    return user_can_menu_action(user, module_key, menu_key, 'edit')


def user_can_access_any_menu(user, module_key: str) -> bool:
    if not module_has_submenus(module_key):
        from hrm.role_permissions import role_allows_view
        return role_allows_view(user, module_key)

    mod_perm = get_user_module_perm(user, module_key)
    if not module_has_configured_menus(mod_perm):
        from hrm.role_permissions import role_allows_view
        return role_allows_view(user, module_key)

    menus = mod_perm.get('menus', {})
    return any(module_perm_allows_view(menus.get(m['key'], empty_module_perm())) for m in get_module_submenus(module_key))


def resolve_menu_from_request(path: str, tab: str | None = None) -> tuple[str | None, str | None]:
    """Trả về (module_key, menu_key) từ URL. menu_key None nếu không xác định được menu con."""
    from hrm.module_permissions import resolve_module_from_request

    module_key = resolve_module_from_request(path, tab)
    if not module_key or not module_has_submenus(module_key):
        return module_key, None

    for prefix, rule_module, menu_key in MENU_PATH_RULES:
        if rule_module != module_key:
            continue
        if path.startswith(prefix):
            return module_key, menu_key

    return module_key, None


def menu_access_denied_message(module_key: str, menu_key: str) -> str:
    module_label = MODULE_LABELS.get(module_key, module_key)
    menu_label = get_menu_label(module_key, menu_key)
    return (
        f'Nhóm quyền của bạn không được phép truy cập "{menu_label}" '
        f'(thuộc {module_label}). Liên hệ HR hoặc IT nếu cần quyền.'
    )


def handle_menu_access_denied(request, module_key: str, menu_key: str):
    from django.contrib import messages
    from django.http import JsonResponse
    from django.shortcuts import redirect

    message = menu_access_denied_message(module_key, menu_key)
    accept = request.headers.get('Accept', '')
    if (
        'application/json' in accept
        or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.headers.get('X-CSRFToken')
    ):
        return JsonResponse({'status': 'error', 'message': message}, status=403)

    messages.error(request, message)
    return redirect('home_portal')

