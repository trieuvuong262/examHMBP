"""Tiêu đề tab trình duyệt theo menu/URL portal."""

from hrm.menu_permissions import resolve_menu_from_request
from hrm.module_permissions import (
    DEPARTMENT_MODULE_LABELS,
    MODULE_LABELS,
    resolve_module_from_request,
)
from hrm.submenu_registry import get_menu_label

SITE_TITLE = 'Just Play Portal'

_STATIC_PATH_TITLES = (
    ('/accounts/login/', 'Đăng nhập'),
    ('/change-password', 'Thiết lập mật khẩu'),
)


def _module_label(module_key: str) -> str:
    return DEPARTMENT_MODULE_LABELS.get(module_key) or MODULE_LABELS.get(module_key, module_key)


def resolve_page_title(path: str, tab: str | None = None) -> str:
    """Trả về tiêu đề tab: «Menu - Just Play Portal» hoặc chỉ tên site."""
    normalized = path or '/'
    if normalized in ('', '/'):
        return f'Trang chủ - {SITE_TITLE}'

    for prefix, label in _STATIC_PATH_TITLES:
        if normalized.startswith(prefix):
            return f'{label} - {SITE_TITLE}'

    module_key, menu_key = resolve_menu_from_request(normalized, tab)
    if not module_key:
        module_key = resolve_module_from_request(normalized, tab)

    if not module_key:
        return SITE_TITLE

    module_label = _module_label(module_key)
    if menu_key:
        menu_label = get_menu_label(module_key, menu_key)
        if menu_label and menu_label != module_label:
            return f'{menu_label} - {module_label} - {SITE_TITLE}'

    return f'{module_label} - {SITE_TITLE}'
