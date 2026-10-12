"""Vai trò trên hồ sơ chỉ chọn được nhân sự thuộc phòng ban / bộ phận tương ứng (tính cả kiêm nhiệm).

Tên khớp với danh mục Phòng ban / Bộ phận của HRM — đổi tên bên HRM thì sửa ở đây.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Q

from .models import Role

ROLE_SCOPES = {
    Role.DESIGNER: {'divisions': ('THIẾT KẾ SẢN PHẨM',)},
    Role.TECHNICIAN: {'divisions': ('IE',)},
    Role.SAMPLE_MAKER: {'divisions': ('MAY MẪU',)},
    Role.COSTING: {'departments': ('KẾ HOẠCH SẢN XUẤT',), 'divisions': ('KẾ TOÁN',)},
}


def scope_label(role: str) -> str:
    scope = ROLE_SCOPES.get(role)
    if not scope:
        return ''
    return 'Nhân sự thuộc: ' + ', '.join([*scope.get('departments', ()), *scope.get('divisions', ())])


def user_filter(role: str) -> Q | None:
    """Q lọc user theo phòng ban / bộ phận của vai trò; None = vai trò không giới hạn."""
    scope = ROLE_SCOPES.get(role)
    if not scope:
        return None
    match = Q()
    for name in scope.get('departments', ()):
        match |= Q(profile__department__name__iexact=name)
        match |= Q(
            profile__concurrent_positions__is_active=True,
            profile__concurrent_positions__department__name__iexact=name,
        )
    for name in scope.get('divisions', ()):
        match |= Q(profile__division__name__iexact=name)
        match |= Q(
            profile__concurrent_positions__is_active=True,
            profile__concurrent_positions__division__name__iexact=name,
        )
    return Q(pk__in=get_user_model().objects.filter(match).values('pk'))
