"""Quyền truy cập trang Tải NAS (bộ cài Windows)."""

from hrm.menu_permissions import user_can_access_menu
from hrm.module_permissions import MODULE_NAS_STORAGE


def user_can_nas_download(user) -> bool:
    """Mọi user được duyệt NAS trên Portal đều có thể tải bộ cài."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if user_can_access_menu(user, MODULE_NAS_STORAGE, 'nas_download'):
        return True
    return user_can_access_menu(user, MODULE_NAS_STORAGE, 'browse')
