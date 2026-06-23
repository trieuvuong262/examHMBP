"""URL và menu báo cáo — tách SX (sản xuất) / VP (văn phòng)."""

from urllib.parse import urlencode

from django.urls import reverse

from hrm.menu_permissions import user_can_access_menu
from hrm.module_permissions import MODULE_REPORTS
from reports.report_profile import (
    REPORT_PROFILE_OFFICE,
    REPORT_PROFILE_PRODUCTION,
)
from reports.period_utils import (
    PERIOD_DAY,
    PERIOD_MONTH,
    PERIOD_WEEK,
    period_query_param,
)

MENU_DAILY_CN = 'daily_cn'
MENU_DAILY_CN_DETAIL = 'daily_cn_detail'
MENU_DAILY_VP = 'daily_vp'
MENU_DAILY_VP_DETAIL = 'daily_vp_detail'

MENU_WEEKLY_CN = 'weekly_cn'
MENU_WEEKLY_CN_DETAIL = 'weekly_cn_detail'
MENU_WEEKLY_VP = 'weekly_vp'
MENU_WEEKLY_VP_DETAIL = 'weekly_vp_detail'

_LEGACY_DAILY_MENU_ALIASES = {
    MENU_DAILY_CN: 'daily',
    MENU_DAILY_CN_DETAIL: 'daily',
    MENU_DAILY_VP: 'daily',
    MENU_DAILY_VP_DETAIL: 'daily',
}

_LEGACY_WEEKLY_MENU_ALIASES = {
    MENU_WEEKLY_CN: 'weekly',
    MENU_WEEKLY_CN_DETAIL: 'weekly',
    MENU_WEEKLY_VP: 'weekly',
    MENU_WEEKLY_VP_DETAIL: 'weekly',
}


def legacy_daily_menu_key(menu_key: str) -> str | None:
    return _LEGACY_DAILY_MENU_ALIASES.get(menu_key)


def legacy_weekly_menu_key(menu_key: str) -> str | None:
    return _LEGACY_WEEKLY_MENU_ALIASES.get(menu_key)


def legacy_reports_menu_key(menu_key: str) -> str | None:
    return legacy_daily_menu_key(menu_key) or legacy_weekly_menu_key(menu_key)


def today_url_name_for_user(user) -> str:
    """Ưu tiên menu được cấp trong phân quyền — không theo phòng ban."""
    if user_can_access_menu(user, MODULE_REPORTS, MENU_DAILY_CN):
        return 'reports:today_cn'
    if user_can_access_menu(user, MODULE_REPORTS, MENU_DAILY_VP):
        return 'reports:today_vp'
    return 'reports:today_cn'


def today_url_for_user(user) -> str:
    return reverse(today_url_name_for_user(user))


def weekly_url_name_for_user(user) -> str:
    if user_can_access_menu(user, MODULE_REPORTS, MENU_WEEKLY_CN):
        return 'reports:weekly_cn'
    if user_can_access_menu(user, MODULE_REPORTS, MENU_WEEKLY_VP):
        return 'reports:weekly_vp'
    return 'reports:weekly_cn'


def weekly_url_for_user(user) -> str:
    return reverse(weekly_url_name_for_user(user))


def my_url_name_for_user(user) -> str:
    if user_can_access_menu(user, MODULE_REPORTS, MENU_DAILY_CN):
        return 'reports:my_cn'
    if user_can_access_menu(user, MODULE_REPORTS, MENU_DAILY_VP):
        return 'reports:my_vp'
    if user_can_access_menu(user, MODULE_REPORTS, MENU_WEEKLY_CN):
        return 'reports:my_cn'
    if user_can_access_menu(user, MODULE_REPORTS, MENU_WEEKLY_VP):
        return 'reports:my_vp'
    if user_can_access_menu(user, MODULE_REPORTS, MENU_DAILY_CN_DETAIL):
        return 'reports:my_cn'
    if user_can_access_menu(user, MODULE_REPORTS, MENU_DAILY_VP_DETAIL):
        return 'reports:my_vp'
    return 'reports:my_cn'


def my_url_for_user(user) -> str:
    return reverse(my_url_name_for_user(user))


def team_url_name_for_profile(report_profile: str) -> str:
    if report_profile == REPORT_PROFILE_PRODUCTION:
        return 'reports:team_cn'
    return 'reports:team_vp'


def team_url_for_profile(report_profile: str) -> str:
    return reverse(team_url_name_for_profile(report_profile))


def team_weekly_url_name_for_profile(report_profile: str) -> str:
    if report_profile == REPORT_PROFILE_PRODUCTION:
        return 'reports:team_weekly_cn'
    return 'reports:team_weekly_vp'


def team_weekly_url_for_profile(report_profile: str) -> str:
    return reverse(team_weekly_url_name_for_profile(report_profile))


def my_url_name_for_profile(report_profile: str) -> str:
    if report_profile == REPORT_PROFILE_PRODUCTION:
        return 'reports:my_cn'
    return 'reports:my_vp'


def my_url_for_profile(report_profile: str) -> str:
    return reverse(my_url_name_for_profile(report_profile))


def page_tools_context_for_profile(report_profile: str, *, report_period: str = 'daily') -> dict:
    """Context cho nút Lịch sử / cấp dưới trên trang nhập báo cáo."""
    return {
        'report_period': report_period,
        'my_url_name': my_url_name_for_profile(report_profile),
        'team_url_name': team_url_name_for_profile(report_profile),
        'team_weekly_url_name': team_weekly_url_name_for_profile(report_profile),
        'today_url_name': (
            'reports:today_cn'
            if report_profile == REPORT_PROFILE_PRODUCTION
            else 'reports:today_vp'
        ),
        'weekly_url_name': weekly_url_name_for_profile(report_profile),
    }


def weekly_url_name_for_profile(report_profile: str) -> str:
    if report_profile == REPORT_PROFILE_PRODUCTION:
        return 'reports:weekly_cn'
    return 'reports:today_vp'


def weekly_url_for_profile(report_profile: str) -> str:
    return reverse(weekly_url_name_for_profile(report_profile))


def copy_prev_week_url_name_for_profile(report_profile: str) -> str:
    if report_profile == REPORT_PROFILE_PRODUCTION:
        return 'reports:copy_prev_week_cn'
    return 'reports:copy_prev_week_vp'


def weekly_detail_url_name_for_profile(report_profile: str) -> str:
    if report_profile == REPORT_PROFILE_PRODUCTION:
        return 'reports:weekly_detail_cn'
    return 'reports:weekly_detail_vp'


def weekly_detail_url_name_for_report(report) -> str:
    if getattr(report, 'is_production_report', False):
        return 'reports:weekly_detail_cn'
    return 'reports:weekly_detail_vp'


def weekly_detail_url_for_report(report) -> str:
    return reverse(weekly_detail_url_name_for_report(report), kwargs={'pk': report.pk})


def detail_url_name_for_report(report) -> str:
    if report.is_production_report:
        return 'reports:detail_cn'
    return 'reports:detail_vp'


def detail_url_for_report(report) -> str:
    return reverse(detail_url_name_for_report(report), kwargs={'pk': report.pk})


def detail_export_url_name_for_report(report) -> str:
    if report.is_production_report:
        return 'reports:detail_export_cn'
    return 'reports:detail_export_vp'


def detail_export_url_for_report(report) -> str:
    return reverse(detail_export_url_name_for_report(report), kwargs={'pk': report.pk})


def can_view_own_report_history(user, report_profile: str | None) -> bool:
    """Xem lịch sử báo cáo cá nhân — theo menu ngày/tuần, không cần quyền quản lý."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if report_profile == REPORT_PROFILE_PRODUCTION:
        return (
            user_can_access_menu(user, MODULE_REPORTS, MENU_DAILY_CN)
            or user_can_access_menu(user, MODULE_REPORTS, MENU_WEEKLY_CN)
        )
    if report_profile == REPORT_PROFILE_OFFICE:
        return (
            user_can_access_menu(user, MODULE_REPORTS, MENU_DAILY_VP)
            or user_can_access_menu(user, MODULE_REPORTS, MENU_WEEKLY_VP)
        )
    return (
        user_can_access_menu(user, MODULE_REPORTS, MENU_DAILY_CN)
        or user_can_access_menu(user, MODULE_REPORTS, MENU_DAILY_VP)
        or user_can_access_menu(user, MODULE_REPORTS, MENU_WEEKLY_CN)
        or user_can_access_menu(user, MODULE_REPORTS, MENU_WEEKLY_VP)
    )


def history_url_for(report, viewer) -> str:
    profile = (
        REPORT_PROFILE_PRODUCTION
        if getattr(report, 'is_production_report', False)
        else getattr(report, 'report_profile', REPORT_PROFILE_OFFICE)
    )
    base = my_url_for_profile(profile)
    params = {}
    if hasattr(report, 'week_start'):
        if profile == REPORT_PROFILE_OFFICE:
            params['period'] = PERIOD_WEEK
        else:
            params['period'] = 'weekly'
    elif getattr(report, 'report_period', PERIOD_DAY) not in (PERIOD_DAY, '', None):
        params['period'] = report.report_period
    if report.employee_id != viewer.id:
        params['for_user'] = report.employee_id
    if not params:
        return base
    return f'{base}?{urlencode(params)}'


def list_back_url_for(report, viewer, *, can_view_team: bool) -> str:
    profile = (
        REPORT_PROFILE_PRODUCTION
        if report.is_production_report
        else REPORT_PROFILE_OFFICE
    )
    if report.employee_id != viewer.id and can_view_team:
        if hasattr(report, 'week_start'):
            if profile == REPORT_PROFILE_OFFICE:
                return (
                    f"{team_url_for_profile(profile)}"
                    f"?{urlencode(period_query_param(PERIOD_WEEK, report.week_start))}"
                )
            return (
                f"{team_weekly_url_for_profile(profile)}"
                f"?week={report.week_start.isoformat()}"
            )
        if not report.is_production_report:
            return (
                f"{team_url_for_profile(profile)}"
                f"?{urlencode(period_query_param(report.report_period, report.report_date))}"
            )
        return f"{team_url_for_profile(profile)}?date={report.report_date.isoformat()}"
    base = my_url_for_profile(profile)
    if hasattr(report, 'week_start'):
        if profile == REPORT_PROFILE_OFFICE:
            return f'{base}?period={PERIOD_WEEK}'
        return f'{base}?period=weekly'
    if not report.is_production_report and report.report_period != PERIOD_DAY:
        return f'{base}?period={report.report_period}'
    return base


def redirect_team_legacy(user):
    """URL quản lý báo cáo ngày mặc định — theo phân quyền menu."""
    if user_can_access_menu(user, MODULE_REPORTS, MENU_DAILY_CN_DETAIL):
        return reverse('reports:team_cn')
    if user_can_access_menu(user, MODULE_REPORTS, MENU_DAILY_VP_DETAIL):
        return reverse('reports:team_vp')
    return reverse('reports:team_cn')


def team_pending_url_for_user(user) -> str:
    """Trang team lọc «Chưa nộp» — khớp widget việc cần làm trên trang chủ."""
    return f'{redirect_team_legacy(user)}?status=missing'


def redirect_team_weekly_legacy(user):
    """URL quản lý báo cáo tuần VP (đã gộp vào team_vp) — SX chuyển về team ngày."""
    if user_can_access_menu(user, MODULE_REPORTS, MENU_WEEKLY_CN_DETAIL):
        return reverse('reports:team_cn')
    if user_can_access_menu(user, MODULE_REPORTS, MENU_DAILY_VP_DETAIL):
        return reverse('reports:team_vp') + f'?period={PERIOD_WEEK}'
    if user_can_access_menu(user, MODULE_REPORTS, MENU_WEEKLY_VP_DETAIL):
        return reverse('reports:team_vp') + f'?period={PERIOD_WEEK}'
    return reverse('reports:team_cn')


def redirect_copy_yesterday_legacy(user):
    if user_can_access_menu(user, MODULE_REPORTS, MENU_DAILY_CN):
        return reverse('reports:copy_yesterday_cn')
    if user_can_access_menu(user, MODULE_REPORTS, MENU_DAILY_VP):
        return reverse('reports:copy_yesterday_vp')
    return reverse('reports:copy_yesterday_cn')


def redirect_copy_prev_week_legacy(user):
    if user_can_access_menu(user, MODULE_REPORTS, MENU_DAILY_VP):
        return reverse('reports:copy_prev_vp') + f'?period={PERIOD_WEEK}'
    if user_can_access_menu(user, MODULE_REPORTS, MENU_WEEKLY_VP):
        return reverse('reports:copy_prev_vp') + f'?period={PERIOD_WEEK}'
    if user_can_access_menu(user, MODULE_REPORTS, MENU_WEEKLY_CN):
        return reverse('reports:copy_prev_week_cn')
    return reverse('reports:copy_prev_week_cn')


def report_profile_label(report_profile: str) -> str:
    if report_profile == REPORT_PROFILE_PRODUCTION:
        return 'SX'
    return 'VP'
