"""Phân quyền IE master data — tách IE (lập) / Approver (duyệt).

Theo 00_HUONG_DAN mục 4:
- IE: tạo đề nghị mã CĐ, lập routing, đo thời gian, phân tích SMV.
- Người phê duyệt master data: duyệt OP_CODE/REV, routing revision.

Quyền duyệt: menu «Duyệt phát hành» (ie_approve) — action Sửa trong Phân quyền.
Superuser/admin (bypass) luôn được duyệt.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from hrm.module_permissions import (
    MODULE_SAN_XUAT,
    bypass_department_modules,
    user_can_update_module,
)

IE_APPROVER_GROUP = 'SX_IE_Approver'


def ensure_ie_approver_group() -> Group:
    group, _ = Group.objects.get_or_create(name=IE_APPROVER_GROUP)
    return group


def ie_approver_group_has_members() -> bool:
    return ensure_ie_approver_group().user_set.exists()


def user_can_approve_ie(user) -> bool:
    """Được duyệt OP / routing — quyền Sửa menu «Duyệt phát hành» trong Phân quyền."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if bypass_department_modules(user):
        return True
    from hrm.menu_permissions import user_can_update_menu

    return user_can_update_menu(user, MODULE_SAN_XUAT, 'ie_approve')


def user_is_ie_editor(user) -> bool:
    """IE lập/sửa dữ liệu (không gồm duyệt phát hành)."""
    return user_can_update_module(user, MODULE_SAN_XUAT)


def ie_user_display_name(user) -> str:
    """Họ tên ưu tiên, không thì username — dùng cho Người lập / Người duyệt."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return ''
    name = (getattr(user, 'get_full_name', lambda: '')() or '').strip()
    return (name or getattr(user, 'username', '') or '')[:120]


def list_ie_approvers():
    return list(ensure_ie_approver_group().user_set.order_by('username'))


def list_ie_approver_candidates(*, limit: int = 300):
    User = get_user_model()
    return list(User.objects.filter(is_active=True).order_by('username')[:limit])


def add_ie_approver_by_username(username: str):
    """Thêm user vào nhóm Approver. Trả (user, created_bool). Raise ValueError nếu không tìm thấy."""
    username = (username or '').strip()
    if not username:
        raise ValueError('Nhập username.')
    User = get_user_model()
    user = User.objects.filter(username__iexact=username).first()
    if not user:
        raise ValueError(f'Không tìm thấy user «{username}».')
    group = ensure_ie_approver_group()
    created = not group.user_set.filter(pk=user.pk).exists()
    group.user_set.add(user)
    return user, created


def remove_ie_approver_by_username(username: str):
    """Gỡ user khỏi nhóm Approver. Trả user. Raise ValueError nếu không tìm thấy."""
    username = (username or '').strip()
    if not username:
        raise ValueError('Nhập username.')
    User = get_user_model()
    user = User.objects.filter(username__iexact=username).first()
    if not user:
        raise ValueError(f'Không tìm thấy user «{username}».')
    ensure_ie_approver_group().user_set.remove(user)
    return user
