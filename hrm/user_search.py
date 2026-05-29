"""Tìm kiếm danh sách nhân sự — server-side, qua mọi trang phân trang."""

from django.contrib.auth.models import User
from django.db.models import Q


def filter_users_by_search(queryset, query: str):
    """Lọc user theo từ khóa (mã NS, tên, account, email, phòng ban, bộ phận…)."""
    text = (query or '').strip()
    if not text:
        return queryset

    terms = [part for part in text.split() if part]
    if not terms:
        return queryset

    for term in terms:
        queryset = queryset.filter(
            Q(username__icontains=term)
            | Q(first_name__icontains=term)
            | Q(last_name__icontains=term)
            | Q(email__icontains=term)
            | Q(profile__full_name__icontains=term)
            | Q(profile__employee_code__icontains=term)
            | Q(profile__job_position__icontains=term)
            | Q(profile__job_title__icontains=term)
            | Q(profile__department__name__icontains=term)
            | Q(profile__division__name__icontains=term)
        )
    return queryset.distinct()


def user_display_label(user: User) -> str:
    """Nhãn hiển thị / tìm trong dropdown nhân viên."""
    profile = getattr(user, 'profile', None)
    full_name = profile.full_name if profile and profile.full_name else user.get_full_name() or user.username
    code = profile.employee_code if profile and profile.employee_code else '—'
    return f'{full_name} · {code} · {user.username}'
