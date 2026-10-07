"""Phân quyền cập nhật avatar — không mặc định cho mọi nhân viên."""

from hrm.group_permissions import get_user_group_permissions
from hrm.module_permissions import (
    MODULE_HRM,
    MODULE_RECRUITMENT,
    bypass_department_modules,
    user_can_update_module,
)

EXTRA_UPDATE_OWN_AVATAR = 'update_own_avatar'
# Tuyển dụng: bỏ giới hạn «chỉ vị trí mình quản lý» (HCNS, TGĐ) — xem recruitment.permissions.
EXTRA_RECRUITMENT_ALL_DEPARTMENTS = 'all_departments'

# Quyền bổ sung theo module (registry dùng chung cho ma trận nhóm quyền).
MODULE_EXTRA_PERMS = {
    MODULE_HRM: (EXTRA_UPDATE_OWN_AVATAR,),
    MODULE_RECRUITMENT: (EXTRA_RECRUITMENT_ALL_DEPARTMENTS,),
}

EXTRA_PERM_LABELS = {
    EXTRA_UPDATE_OWN_AVATAR: 'Cập nhật avatar cá nhân',
    EXTRA_RECRUITMENT_ALL_DEPARTMENTS: 'Tuyển dụng — xem ứng viên mọi phòng ban',
}


def extra_field_name(module_key: str, extra_key: str) -> str:
    return f'extra_{module_key}_{extra_key}'


def _hrm_extras(user) -> dict:
    hrm = get_user_group_permissions(user).get(MODULE_HRM, {})
    extras = hrm.get('extras')
    return extras if isinstance(extras, dict) else {}


def user_can_update_own_avatar(user) -> bool:
    """Quyền đổi avatar của chính mình (sidebar / profile) — chỉ qua extra, không gộp quyền Sửa HRM."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if bypass_department_modules(user):
        return True
    return bool(_hrm_extras(user).get(EXTRA_UPDATE_OWN_AVATAR))


def user_can_update_profile_avatar(actor, target_profile) -> bool:
    """Quyền đổi avatar của một hồ sơ — bản thân hoặc nhân sự khác (form HRM)."""
    if not getattr(actor, 'is_authenticated', False):
        return False
    if bypass_department_modules(actor):
        return True
    owner = getattr(target_profile, 'user', None)
    if owner is not None and owner.pk == actor.pk:
        return user_can_update_own_avatar(actor)
    return user_can_update_module(actor, MODULE_HRM)
