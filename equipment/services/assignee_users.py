"""Queryset người sử dụng thiết bị — ưu tiên nhân viên cấp dưới."""

from __future__ import annotations

from django.contrib.auth import get_user_model

User = get_user_model()


def equipment_assignee_queryset(viewer, *, current_user_id=None):
    """
    Trả về queryset cho ô «Người sử dụng».
    Nếu người sửa có cấp dưới (M2M / kiêm nhiệm / auto scope) thì chỉ liệt kê cấp dưới;
    ngược lại dùng toàn bộ nhân viên đang làm việc.
    Luôn giữ người đang được gán (khi sửa) nếu họ không nằm trong danh sách.
    """
    from hrm.concurrent_positions import get_effective_subordinate_users

    if not viewer or not getattr(viewer, 'is_authenticated', False):
        qs = User.objects.filter(profile__is_employed=True)
    else:
        sub_qs = get_effective_subordinate_users(viewer)
        if sub_qs.exists():
            qs = sub_qs.filter(profile__is_employed=True)
        else:
            qs = User.objects.filter(profile__is_employed=True)

    if current_user_id:
        qs = (qs | User.objects.filter(pk=current_user_id)).distinct()

    return qs.select_related('profile', 'profile__department').order_by(
        'profile__full_name', 'username',
    )
