"""Loại báo cáo theo phòng ban — PRODUCTION vs OFFICE."""

from hrm.permissions import get_profile

REPORT_PROFILE_PRODUCTION = 'PRODUCTION'
REPORT_PROFILE_OFFICE = 'OFFICE'

REPORT_PROFILE_CHOICES = (
    (REPORT_PROFILE_PRODUCTION, 'Sản xuất (bảng năng suất)'),
    (REPORT_PROFILE_OFFICE, 'Phòng ban khác (Excel / Word tự do)'),
)

# Tên phòng ban mặc định dùng form sản xuất (HR có thể đổi trên form phòng ban).
DEFAULT_PRODUCTION_DEPARTMENT_NAMES = frozenset({
    'SẢN XUẤT',
    'ĐẢM BẢO CHẤT LƯỢNG',
})


def default_report_profile_for_department_name(name: str) -> str:
    normalized = (name or '').strip().upper()
    if normalized in DEFAULT_PRODUCTION_DEPARTMENT_NAMES:
        return REPORT_PROFILE_PRODUCTION
    if 'SẢN XUẤT' in normalized and 'KẾ HOẠCH' not in normalized:
        return REPORT_PROFILE_PRODUCTION
    return REPORT_PROFILE_OFFICE


def get_report_profile(user) -> str:
    """Profile báo cáo của NV — lấy từ phòng ban; mặc định OFFICE."""
    profile = get_profile(user)
    if not profile or not profile.department_id:
        return REPORT_PROFILE_OFFICE
    department = profile.department
    return getattr(department, 'report_profile', None) or REPORT_PROFILE_OFFICE


def is_production_report_user(user) -> bool:
    return get_report_profile(user) == REPORT_PROFILE_PRODUCTION
