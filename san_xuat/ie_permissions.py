"""Phân quyền IE master data — tách IE (lập) / Approver (duyệt).

Theo 00_HUONG_DAN mục 4:
- IE: tạo đề nghị mã CĐ, lập routing, đo thời gian, phân tích SMV.
- Người phê duyệt master data: duyệt OP_CODE/REV, routing revision.

Nhóm Django: ``SX_IE_Approver``. Superuser/admin luôn được duyệt.
Khi nhóm chưa có thành viên nào → tạm cho phép user có quyền cập nhật SX (bootstrap).
"""

from __future__ import annotations

from django.contrib.auth.models import Group

from hrm.module_permissions import (
    MODULE_SAN_XUAT,
    bypass_department_modules,
    user_can_access_module,
    user_can_update_module,
)

IE_APPROVER_GROUP = 'SX_IE_Approver'


def ensure_ie_approver_group() -> Group:
    group, _ = Group.objects.get_or_create(name=IE_APPROVER_GROUP)
    return group


def ie_approver_group_has_members() -> bool:
    return ensure_ie_approver_group().user_set.exists()


def user_can_approve_ie(user) -> bool:
    """Được duyệt OP / routing / time-study cập nhật SMV phát hành."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if bypass_department_modules(user):
        return True
    if not user_can_access_module(user, MODULE_SAN_XUAT):
        return False
    group = ensure_ie_approver_group()
    if group.user_set.exists():
        return group.user_set.filter(pk=user.pk).exists()
    # Bootstrap: chưa gán Approver → giữ hành vi cũ (update = duyệt)
    return user_can_update_module(user, MODULE_SAN_XUAT)


def user_is_ie_editor(user) -> bool:
    """IE lập/sửa dữ liệu (không gồm duyệt phát hành)."""
    return user_can_update_module(user, MODULE_SAN_XUAT)
