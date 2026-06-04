"""Quyền truy cập module KiotViet trên portal."""

from hrm.module_permissions import MODULE_KIOTVIET, bypass_department_modules, user_can_access_module
from hrm.permissions import is_portal_admin

from .client import KiotVietClient


def kiotviet_is_live() -> bool:
    """API đã bật và đủ credentials trên server."""
    return KiotVietClient.is_configured()


def user_can_use_kiotviet(user) -> bool:
    if not kiotviet_is_live():
        return False
    if bypass_department_modules(user) or is_portal_admin(user):
        return True
    return user_can_access_module(user, MODULE_KIOTVIET)
