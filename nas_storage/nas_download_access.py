"""Quyền truy cập trang Tải bộ cài (Windows)."""

from hrm.menu_permissions import user_can_access_menu
from hrm.module_permissions import MODULE_DOCUMENTS, MODULE_NAS_STORAGE


def user_can_nas_download(user) -> bool:
    """Mọi user được duyệt tải bộ cài (Thư viện) vẫn tải được như trước."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if user_can_access_menu(user, MODULE_DOCUMENTS, 'nas_download'):
        return True
    if user_can_access_menu(user, MODULE_DOCUMENTS, 'browse'):
        return True
    # Tương thích nhóm chưa chạy migration / quyền cũ dưới NAS
    if user_can_access_menu(user, MODULE_NAS_STORAGE, 'nas_download'):
        return True
    return user_can_access_menu(user, MODULE_NAS_STORAGE, 'browse')
