"""Quyền truy cập trang Tải bộ cài (Windows)."""

from django.conf import settings
from django.urls import reverse

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


def raidrive_installer_context(request) -> dict:
    """URL tải RaiDrive cho header / trang Tải bộ cài (không cần quyền NAS browse)."""
    token = getattr(settings, 'NAS_RAIDRIVE_INSTALLER_SHARE_TOKEN', '').strip()
    if not token:
        return {'raidrive_share_url': '', 'raidrive_file_name': ''}

    from nas_storage.share_access import get_active_share

    share = get_active_share(token)
    try:
        url = request.build_absolute_uri(reverse('documents:raidrive_download'))
    except Exception:
        url = ''
    return {
        'raidrive_share_url': url,
        'raidrive_file_name': (share.item_name if share else 'RaiDrive_x64.exe'),
    }
