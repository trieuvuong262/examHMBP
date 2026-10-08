"""Quyền module Thiết kế sản phẩm = quyền menu (Phân quyền) × vai trò trên từng hồ sơ.

- Menu «Hồ sơ sản phẩm»: Xem / Thêm (tạo đề xuất) / Sửa (cập nhật nội dung theo vai trò) / Xóa (xóa nháp).
- Menu «Duyệt hồ sơ»: Sửa = được chọn làm Người duyệt và ra quyết định duyệt.
- Menu «Thiết lập»: Sửa = cấu hình số ngày chuẩn, người nhận bàn giao.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Q

from hrm.menu_permissions import (
    user_can_access_resolved_menu,
    user_can_create_menu,
    user_can_delete_menu,
    user_can_update_menu,
)
from hrm.module_permissions import MODULE_THIET_KE_SP, bypass_department_modules

from .models import DOSSIER_ROLE_FIELDS, FINAL_STATUSES, ProductDevelopment, Role, Status

MENU_DASHBOARD = 'dashboard'
MENU_DOSSIERS = 'dossiers'
MENU_MY_TASKS = 'my_tasks'
MENU_APPROVE = 'approve'
MENU_SETTINGS = 'settings'


def is_admin(user) -> bool:
    return bypass_department_modules(user)


def can_view_module(user) -> bool:
    return user_can_access_resolved_menu(user, MODULE_THIET_KE_SP, MENU_DOSSIERS)


def can_create(user) -> bool:
    return user_can_create_menu(user, MODULE_THIET_KE_SP, MENU_DOSSIERS)


def can_update(user) -> bool:
    return user_can_update_menu(user, MODULE_THIET_KE_SP, MENU_DOSSIERS)


def can_delete(user) -> bool:
    return user_can_delete_menu(user, MODULE_THIET_KE_SP, MENU_DOSSIERS)


def has_approve_permission(user) -> bool:
    return user_can_update_menu(user, MODULE_THIET_KE_SP, MENU_APPROVE)


def can_manage_settings(user) -> bool:
    return user_can_update_menu(user, MODULE_THIET_KE_SP, MENU_SETTINGS)


def user_roles(dossier: ProductDevelopment, user) -> set[str]:
    if not getattr(user, 'is_authenticated', False):
        return set()
    roles = set()
    if dossier.proposer_id == user.pk:
        roles.add(Role.PROPOSER)
    for field in DOSSIER_ROLE_FIELDS:
        if getattr(dossier, f'{field}_id') == user.pk:
            roles.add(field)
    return roles


def has_role(dossier: ProductDevelopment, user, *roles: str) -> bool:
    if is_admin(user):
        return True
    return bool(user_roles(dossier, user) & set(roles))


def can_work_as(dossier: ProductDevelopment, user, *roles: str) -> bool:
    """Thao tác nghiệp vụ: cần quyền Sửa menu hồ sơ + đúng vai trò trên hồ sơ."""
    if dossier.status in FINAL_STATUSES:
        return False
    return can_update(user) and has_role(dossier, user, *roles)


def is_dossier_approver(dossier: ProductDevelopment, user) -> bool:
    if dossier.status in FINAL_STATUSES:
        return False
    if is_admin(user):
        return True
    return dossier.approver_id == user.pk and has_approve_permission(user)


def can_edit_brief(dossier: ProductDevelopment, user) -> bool:
    if dossier.status not in (Status.DRAFT, Status.BRIEF_NEEDS_INFO):
        return False
    return can_update(user) and has_role(dossier, user, Role.PROPOSER, Role.OWNER)


def can_edit_roles(dossier: ProductDevelopment, user) -> bool:
    if dossier.status in FINAL_STATUSES:
        return False
    return can_update(user) and (has_role(dossier, user, Role.OWNER) or is_dossier_approver(dossier, user))


def is_participant(dossier: ProductDevelopment, user) -> bool:
    return is_admin(user) or bool(user_roles(dossier, user))


def approver_candidates():
    """Người có quyền Sửa menu «Duyệt hồ sơ» — lọc thô theo nhóm quyền rồi kiểm tra lại từng người."""
    from hrm.models import PermissionGroup

    User = get_user_model()
    group_ids = []
    for group in PermissionGroup.objects.all():
        module = (group.module_permissions or {}).get(MODULE_THIET_KE_SP) or {}
        menu = (module.get('menus') or {}).get(MENU_APPROVE) or {}
        if menu.get('update') or (not module.get('menus') and module.get('update')):
            group_ids.append(group.pk)
    rough = (
        User.objects.filter(is_active=True)
        .filter(Q(is_superuser=True) | Q(username='admin') | Q(profile__permission_group_id__in=group_ids))
        .select_related('profile')
        .order_by('first_name', 'username')
        .distinct()
    )
    return [u for u in rough if has_approve_permission(u)]


def display_name(user) -> str:
    if user is None:
        return ''
    profile = getattr(user, 'profile', None)
    name = (getattr(profile, 'full_name', '') or '').strip() if profile else ''
    return name or (user.get_full_name() or '').strip() or user.username
