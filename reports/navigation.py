"""URL và menu báo cáo ngày — tách CN (sản xuất) / VP (văn phòng)."""

from django.urls import reverse

from hrm.menu_permissions import user_can_access_menu
from hrm.module_permissions import MODULE_REPORTS
from reports.report_profile import (
    REPORT_PROFILE_OFFICE,
    REPORT_PROFILE_PRODUCTION,
    get_report_profile,
    is_production_report_user,
)

MENU_DAILY_CN = 'daily_cn'
MENU_DAILY_CN_DETAIL = 'daily_cn_detail'
MENU_DAILY_VP = 'daily_vp'
MENU_DAILY_VP_DETAIL = 'daily_vp_detail'

_LEGACY_DAILY_MENU_ALIASES = {
    MENU_DAILY_CN: 'daily',
    MENU_DAILY_CN_DETAIL: 'daily',
    MENU_DAILY_VP: 'daily',
    MENU_DAILY_VP_DETAIL: 'daily',
}


def legacy_daily_menu_key(menu_key: str) -> str | None:
    return _LEGACY_DAILY_MENU_ALIASES.get(menu_key)


def today_url_name_for_user(user) -> str:
    if is_production_report_user(user):
        return 'reports:today_cn'
    return 'reports:today_vp'


def today_url_for_user(user) -> str:
    return reverse(today_url_name_for_user(user))


def team_url_name_for_profile(report_profile: str) -> str:
    if report_profile == REPORT_PROFILE_PRODUCTION:
        return 'reports:team_cn'
    return 'reports:team_vp'


def team_url_for_profile(report_profile: str) -> str:
    return reverse(team_url_name_for_profile(report_profile))


def my_url_name_for_profile(report_profile: str) -> str:
    if report_profile == REPORT_PROFILE_PRODUCTION:
        return 'reports:my_cn'
    return 'reports:my_vp'


def my_url_for_profile(report_profile: str) -> str:
    return reverse(my_url_name_for_profile(report_profile))


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


def history_url_for(report, viewer) -> str:
    profile = (
        REPORT_PROFILE_PRODUCTION
        if report.is_production_report
        else REPORT_PROFILE_OFFICE
    )
    base = my_url_for_profile(profile)
    if report.employee_id == viewer.id:
        return base
    return f'{base}?for_user={report.employee_id}'


def list_back_url_for(report, viewer, *, can_view_team: bool) -> str:
    profile = (
        REPORT_PROFILE_PRODUCTION
        if report.is_production_report
        else REPORT_PROFILE_OFFICE
    )
    if report.employee_id != viewer.id and can_view_team:
        return f"{team_url_for_profile(profile)}?date={report.report_date.isoformat()}"
    return my_url_for_profile(profile)


def redirect_team_legacy(user):
    """URL team mặc định khi truy cập /reports/team/ cũ."""
    if user_can_access_menu(user, MODULE_REPORTS, MENU_DAILY_CN_DETAIL):
        return reverse('reports:team_cn')
    if user_can_access_menu(user, MODULE_REPORTS, MENU_DAILY_VP_DETAIL):
        return reverse('reports:team_vp')
    return reverse('reports:team_cn')


def redirect_hub_for_user(user, *, can_submit: bool, can_view_team: bool, is_director_user: bool):
    if can_view_team and is_director_user:
        return redirect_team_legacy(user)
    if can_submit:
        return today_url_for_user(user)
    if can_view_team:
        return redirect_team_legacy(user)
    return None


def report_profile_label(report_profile: str) -> str:
    if report_profile == REPORT_PROFILE_PRODUCTION:
        return 'CN'
    return 'VP'


def user_report_profile(user) -> str:
    return get_report_profile(user)
