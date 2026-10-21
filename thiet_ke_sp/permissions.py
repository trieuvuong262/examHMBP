"""Quyền module Thiết kế sản phẩm = quyền menu (Phân quyền) × vai trò trên từng hồ sơ.

Tài khoản quản trị không được vượt vai trò: muốn duyệt / thao tác phải được gán đúng vai trò trên hồ sơ.
Ngoại lệ: ``vuong-admin`` và ``ductn`` thao tác được mọi bước trên mọi hồ sơ.

Thành viên hồ sơ (Sản xuất / R&D / Kế hoạch SX / Giám đốc) được xem và thao tác trên hồ sơ mình tham gia
theo vai trò tương ứng, kể cả khi không có quyền menu module.

- Menu «Hồ sơ sản phẩm»: Xem / Thêm (tạo đề xuất) / Sửa (cập nhật nội dung theo vai trò). Ai xem được hồ sơ thì xóa được hồ sơ đó.
- Menu «Chờ tôi duyệt»: Sửa = được chọn làm Người duyệt và ra quyết định duyệt.
- Menu «Thiết lập»: Sửa = cấu hình số ngày chuẩn và danh sách nhân sự được chọn trên hồ sơ.
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
    ROLE_PARTNER,
    APPROVER_DECIDE_STATUSES,
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

# Thao tác mọi bước trên mọi hồ sơ, không cần được gán vai trò.
FULL_DOSSIER_USERNAMES = frozenset({'vuong-admin', 'ductn'})


def has_full_dossier_access(user) -> bool:
    if not getattr(user, 'is_authenticated', False):
        return False
    return (getattr(user, 'username', '') or '').lower() in FULL_DOSSIER_USERNAMES


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


def has_follows(user) -> bool:
    if not getattr(user, 'is_authenticated', False):
        return False
    return ProductDevelopment.objects.filter(followers=user).exists()


def _open_task_qs(user):
    from .models import Task

    return Task.objects.filter(assignee=user, state=Task.STATE_OPEN).exclude(
        dossier__status__in=(Status.PAUSED, Status.CANCELLED, Status.CLOSED),
    )


def has_assigned_work(user) -> bool:
    """Có việc hồ sơ đang mở — kể cả khi không có quyền menu module."""
    if not getattr(user, 'is_authenticated', False):
        return False
    return _open_task_qs(user).exists()


def has_approval_queue(user) -> bool:
    """Có hồ sơ đang chờ chính user này duyệt."""
    if not getattr(user, 'is_authenticated', False):
        return False
    return ProductDevelopment.objects.filter(
        approver=user,
        status__in=APPROVER_DECIDE_STATUSES,
    ).exists()


def is_follower(dossier: ProductDevelopment, user) -> bool:
    if not getattr(user, 'is_authenticated', False) or not getattr(dossier, 'pk', None):
        return False
    return dossier.followers.filter(pk=user.pk).exists()


MEMBER_DOSSIER_URLS = frozenset({'detail', 'action', 'upload', 'delete', 'edit'})
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
        return has_memberships(user) or has_follows(user)
    if name == 'notifications':
        return has_memberships(user) or has_follows(user) or has_assigned_work(user) or has_approval_queue(user)
    if name in ('my_tasks', 'approve_queue'):
        return has_assigned_work(user) or has_approval_queue(user) or has_memberships(user) or has_follows(user)
    if name == 'npl_search':
        return has_memberships(user)
    if name == 'notification_open':
        return True
    if name in MEMBER_DOSSIER_URLS:
        dossier_id = match.kwargs.get('pk')
    elif name in MEMBER_FILE_URLS:
        dossier_id = Attachment.objects.filter(pk=match.kwargs.get('att_pk')).values_list('dossier_id', flat=True).first()
    else:
        return False
    if not dossier_id:
        return False
    dossier = ProductDevelopment.objects.filter(pk=dossier_id).first()
    assigned = bool(dossier and holds_dossier_role(dossier, user))
    if name == 'upload' or name == 'attachment_delete':
        return assigned or DossierMember.objects.filter(dossier_id=dossier_id, user=user).exists()
    if name == 'delete':
        return (
            DossierMember.objects.filter(dossier_id=dossier_id, user=user).exists()
            or ProductDevelopment.objects.filter(pk=dossier_id, followers=user).exists()
        )
    return (
        assigned
        or DossierMember.objects.filter(dossier_id=dossier_id, user=user).exists()
        or ProductDevelopment.objects.filter(pk=dossier_id, followers=user).exists()
    )


def can_view_dossier(dossier: ProductDevelopment, user) -> bool:
    return (
        has_full_dossier_access(user)
        or can_view_module(user)
        or is_member(dossier, user)
        or is_follower(dossier, user)
        or holds_dossier_role(dossier, user)
    )


def can_delete_dossier(dossier: ProductDevelopment, user) -> bool:
    """Xóa theo quyền xem menu / thành viên / người theo dõi. Gán vai trò chưa đủ để xóa."""
    return (
        has_full_dossier_access(user)
        or can_view_module(user)
        or is_member(dossier, user)
        or is_follower(dossier, user)
    )


def holds_dossier_role(dossier: ProductDevelopment, user) -> bool:
    """Được gán một vai trò làm việc trên hồ sơ (không tính thành viên chỉ xem)."""
    if not getattr(user, 'is_authenticated', False):
        return False
    return bool(user_roles(dossier, user) - {Role.MEMBER})


def can_act(dossier: ProductDevelopment, user) -> bool:
    """Quyền Sửa menu, thành viên hồ sơ, hoặc người được gán đúng vai trò trên hồ sơ."""
    return (
        has_full_dossier_access(user)
        or can_update(user)
        or is_member(dossier, user)
        or holds_dossier_role(dossier, user)
    )


def user_roles(dossier: ProductDevelopment, user) -> set[str]:
    if not getattr(user, 'is_authenticated', False):
        return set()
    if has_full_dossier_access(user):
        return {
            Role.PROPOSER, Role.OWNER, Role.APPROVER, Role.DESIGNER, Role.TECHNICIAN,
            Role.SAMPLE_MAKER, Role.QA, Role.COSTING, Role.MEMBER,
        }
    roles = set()
    if dossier.proposer_id == user.pk:
        roles.add(Role.PROPOSER)
    for field in DOSSIER_ROLE_FIELDS:
        if getattr(dossier, f'{field}_id') == user.pk:
            roles.add(field)
    if dossier.co_owner_id == user.pk:
        roles.add(Role.OWNER)
    for role, partner in ROLE_PARTNER.items():
        if getattr(dossier, f'{partner}_id') == user.pk:
            roles.add(role)
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
    if has_full_dossier_access(user):
        return True
    return can_act(dossier, user) and has_role(dossier, user, *roles)


def is_dossier_approver(dossier: ProductDevelopment, user) -> bool:
    if dossier.status in FINAL_STATUSES:
        return False
    if has_full_dossier_access(user):
        return True
    return dossier.approver_id == user.pk and has_approve_permission(user)


def at_overview_step(dossier: ProductDevelopment) -> bool:
    """Hồ sơ đang ở Tổng quan (đề xuất, hoặc đã quay lại / mở lại đúng bước này)."""
    if dossier.status in (Status.DRAFT, Status.BRIEF_NEEDS_INFO, Status.BRIEF_PENDING):
        return True
    if dossier.status == Status.LIBRARY_REOPEN:
        step = (getattr(dossier, 'reopen_edit_step', None) or '').strip()
        return not step or step == 'overview'
    return False


def can_edit_brief(dossier: ProductDevelopment, user) -> bool:
    if dossier.status in (*FINAL_STATUSES, Status.HANDED_OVER):
        return False
    if has_full_dossier_access(user):
        return True
    return has_role(dossier, user, Role.PROPOSER, Role.OWNER)


def can_edit_overview_fields(dossier: ProductDevelopment, user) -> bool:
    """Ở bước Tổng quan, ai xem được hồ sơ cũng sửa tên, khách hàng mục tiêu và đề bài."""
    if not at_overview_step(dossier):
        return False
    if dossier.status in (*FINAL_STATUSES, Status.HANDED_OVER):
        return False
    return can_view_dossier(dossier, user)


def can_edit_roles(dossier: ProductDevelopment, user) -> bool:
    if dossier.status in FINAL_STATUSES:
        return False
    if has_full_dossier_access(user):
        return True
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


AVATAR_TONES = ('#dc2626', '#262626', '#0369a1', '#15803d', '#b45309', '#6d28d9', '#be185d', '#475569')


def user_avatar_url(user) -> str:
    if not getattr(user, 'pk', None):
        return ''
    profile = getattr(user, 'profile', None)
    avatar = getattr(profile, 'avatar', None) if profile is not None else None
    if not avatar:
        return ''
    try:
        return avatar.url or ''
    except (ValueError, OSError):
        return ''


def user_initial(user) -> str:
    name = display_name(user)
    if not name:
        return '?'
    return name.split()[-1][:1].upper()


def avatar_tone_for(value) -> str:
    try:
        return AVATAR_TONES[int(value) % len(AVATAR_TONES)]
    except (TypeError, ValueError):
        return AVATAR_TONES[0]
