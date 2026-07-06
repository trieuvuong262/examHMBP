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


def filter_team_members_for_report_profile(team, report_profile: str):
    """Lọc danh sách NV team theo loại báo cáo.

    SX: NV phòng sản xuất (công nhân).
    VP: NV phòng văn phòng + NV văn phòng trong phòng SX (có quyền «Báo cáo VP» hoặc đã nộp BC VP).
    """
    if report_profile == REPORT_PROFILE_PRODUCTION:
        return team.filter(profile__department__report_profile=REPORT_PROFILE_PRODUCTION)
    if report_profile == REPORT_PROFILE_OFFICE:
        return _office_team_members(team)
    return team


def _office_team_members(team):
    """NV hiển thị trên Quản lý BC (VP) — không loại NV văn phòng trong phòng SX."""
    from hrm.menu_permissions import user_can_access_menu
    from hrm.module_permissions import MODULE_REPORTS

    office_dept = team.exclude(profile__department__report_profile=REPORT_PROFILE_PRODUCTION)
    prod_dept = team.filter(profile__department__report_profile=REPORT_PROFILE_PRODUCTION)
    if not prod_dept.exists():
        return office_dept

    from reports.models import DailyWorkReport

    office_reporter_ids = set(
        DailyWorkReport.objects.filter(
            employee__in=prod_dept,
            report_profile=REPORT_PROFILE_OFFICE,
        ).values_list('employee_id', flat=True).distinct()
    )
    vp_menu_ids = {
        user.pk for user in prod_dept
        if user_can_access_menu(user, MODULE_REPORTS, 'daily_vp')
    }
    extra_ids = office_reporter_ids | vp_menu_ids
    if not extra_ids:
        return office_dept
    return (office_dept | team.filter(pk__in=extra_ids)).distinct()
