"""Quyền truy cập module KiotViet trên portal."""

from hrm.module_permissions import MODULE_KIOTVIET, bypass_department_modules, user_can_access_module

from .mirror import portal_mirror_ready


def kiotviet_is_live() -> bool:
    """Portal tra cứu KiotViet qua mirror DB đã sync."""
    return portal_mirror_ready()


def user_can_use_kiotviet(user) -> bool:
    """Chỉ superuser/username admin (bypass) hoặc module kiotviet được cấp — không theo is_staff."""
    if not kiotviet_is_live():
        return False
    if bypass_department_modules(user):
        return True
    return user_can_access_module(user, MODULE_KIOTVIET)
