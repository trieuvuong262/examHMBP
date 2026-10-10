"""Quyền module Thiết kế sản phẩm = quyền menu (Phân quyền) × vai trò trên từng hồ sơ.

Tài khoản quản trị không được vượt vai trò: muốn duyệt / thao tác phải được gán đúng vai trò trên hồ sơ.

Thành viên hồ sơ (Sản xuất / R&D / Kế hoạch SX / Giám đốc) được xem và thao tác trên hồ sơ mình tham gia
theo vai trò tương ứng, kể cả khi không có quyền menu module.

- Menu «Hồ sơ sản phẩm»: Xem / Thêm (tạo đề xuất) / Sửa (cập nhật nội dung theo vai trò) / Xóa (xóa nháp).
- Menu «Chờ tôi duyệt»: Sửa = được chọn làm Người duyệt và ra quyết định duyệt.
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

from .models import (
    DOSSIER_ROLE_FIELDS,
    FINAL_STATUSES,
    MEMBER_GROUP_ROLES,
    DossierMember,
    ProductDevelopment,
    Role,
    Status,
)

MENU_DASHBOARD = 'dashboard'
MENU_DOSSIERS = 'dossiers'
MENU_KANBAN = 'kanban'
MENU_MY_TASKS = 'my_tasks'
MENU_APPROVE = 'approve'
MENU_REPORTS = 'reports'
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


def _member_groups(dossier: ProductDevelopment) -> dict[int, str]:
    groups = getattr(dossier, '_tksp_member_groups', None)
    if groups is None:
        groups = dict(DossierMember.objects.filter(dossier=dossier).values_list('user_id', 'group'))
        dossier._tksp_member_groups = groups
    return groups


def reset_member_cache(dossier: ProductDevelopment) -> None:
    dossier.__dict__.pop('_tksp_member_groups', None)


def member_group(dossier: ProductDevelopment, user) -> str:
    if not getattr(user, 'is_authenticated', False) or not dossier.pk:
        return ''
    return _member_groups(dossier).get(user.pk, '')


def is_member(dossier: ProductDevelopment, user) -> bool:
    return bool(member_group(dossier, user))


def has_memberships(user) -> bool:
    if not getattr(user, 'is_authenticated', False):
        return False
    return DossierMember.objects.filter(user=user).exclude(dossier__status__in=FINAL_STATUSES).exists()


MEMBER_DOSSIER_URLS = frozenset({'detail', 'action', 'upload'})
MEMBER_FILE_URLS = frozenset({'attachment_serve', 'attachment_delete'})


def member_path_allowed(user, path: str) -> bool:
    """Middleware phân quyền module: thành viên chỉ vào được danh sách và URL của hồ sơ mình tham gia."""
    from django.urls import Resolver404, resolve

    from .models import Attachment

    try:
        match = resolve(path)
    except Resolver404:
        return False
    if match.namespace != 'thiet_ke_sp':
        return False
    name = match.url_name
    if name == 'list':
        return has_memberships(user)
    if name == 'notification_open':
        return True
    if name in MEMBER_DOSSIER_URLS:
        dossier_id = match.kwargs.get('pk')
    elif name in MEMBER_FILE_URLS:
        dossier_id = Attachment.objects.filter(pk=match.kwargs.get('att_pk')).values_list('dossier_id', flat=True).first()
    else:
        return False
    return bool(dossier_id) and DossierMember.objects.filter(dossier_id=dossier_id, user=user).exists()


def can_view_dossier(dossier: ProductDevelopment, user) -> bool:
    return can_view_module(user) or is_member(dossier, user)


def can_act(dossier: ProductDevelopment, user) -> bool:
    """Quyền Sửa menu hồ sơ, hoặc là thành viên của chính hồ sơ này."""
    return can_update(user) or is_member(dossier, user)


def user_roles(dossier: ProductDevelopment, user) -> set[str]:
    if not getattr(user, 'is_authenticated', False):
        return set()
    roles = set()
    if dossier.proposer_id == user.pk:
        roles.add(Role.PROPOSER)
    for field in DOSSIER_ROLE_FIELDS:
        if getattr(dossier, f'{field}_id') == user.pk:
            roles.add(field)
    group = member_group(dossier, user)
    if group:
        roles.add(Role.MEMBER)
        if group in MEMBER_GROUP_ROLES:
            roles.add(MEMBER_GROUP_ROLES[group])
    return roles


def has_role(dossier: ProductDevelopment, user, *roles: str) -> bool:
    return bool(user_roles(dossier, user) & set(roles))


def can_work_as(dossier: ProductDevelopment, user, *roles: str) -> bool:
    """Thao tác nghiệp vụ: cần quyền Sửa menu hồ sơ + đúng vai trò trên hồ sơ."""
    if dossier.status in FINAL_STATUSES:
        return False
    return can_act(dossier, user) and has_role(dossier, user, *roles)


def is_dossier_approver(dossier: ProductDevelopment, user) -> bool:
    if dossier.status in FINAL_STATUSES:
        return False
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
    return bool(user_roles(dossier, user))


def _matrix_allows_approve(matrix: dict) -> bool:
    module = (matrix or {}).get(MODULE_THIET_KE_SP) or {}
    menus = module.get('menus')
    if isinstance(menus, dict) and menus:
        return bool((menus.get(MENU_APPROVE) or {}).get('update'))
    return bool(module.get('update'))


def approver_candidates():
    """Người có quyền Sửa menu «Chờ tôi duyệt» — lọc thô theo ma trận quyền rồi kiểm tra lại từng người."""
    from hrm.group_permissions import permissions_from_legacy_role
    from hrm.models import PermissionGroup, Profile

    User = get_user_model()
    group_ids = [g.pk for g in PermissionGroup.objects.all() if _matrix_allows_approve(g.get_permissions())]
    legacy_roles = [
        role for role in Profile.objects.filter(permission_group__isnull=True).values_list('role', flat=True).distinct()
        if _matrix_allows_approve(permissions_from_legacy_role(role))
    ]
    rough = (
        User.objects.filter(is_active=True)
        .filter(
            Q(is_superuser=True)
            | Q(username='admin')
            | Q(profile__permission_group_id__in=group_ids)
            | Q(profile__permission_group__isnull=True, profile__role__in=legacy_roles)
        )
        .select_related('profile')
        .order_by('profile__full_name', 'username')
        .distinct()
    )
    return [u for u in rough if has_approve_permission(u)]


def display_name(user) -> str:
    if user is None:
        return ''
    profile = getattr(user, 'profile', None)
    name = (getattr(profile, 'full_name', '') or '').strip() if profile else ''
    return name or (user.get_full_name() or '').strip() or user.username
