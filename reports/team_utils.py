"""Tiện ích hiển thị báo cáo cấp dưới — chỉ báo cáo đã lưu nháp hoặc đã nộp."""

from __future__ import annotations

from django.db.models import Q

from hrm.concurrent_positions import MANAGER_SLOT_ROLES, get_active_concurrent_positions
from hrm.permissions import get_profile
from reports.models import DailyWorkReport, WeeklyWorkReport
from reports.period_utils import PERIOD_DAY, PERIOD_MONTH, PERIOD_WEEK
from reports.report_profile import REPORT_PROFILE_OFFICE
from reports.week_utils import monday_of


def meaningful_daily_reports_qs():
    return DailyWorkReport.objects.filter(
        Q(status=DailyWorkReport.STATUS_SUBMITTED)
        | Q(draft_saved_at__isnull=False),
    )


def meaningful_weekly_reports_qs():
    return WeeklyWorkReport.objects.filter(
        Q(status=WeeklyWorkReport.STATUS_SUBMITTED)
        | Q(draft_saved_at__isnull=False),
    )


def daily_report_visible_to_team(report) -> bool:
    if report is None:
        return False
    if report.status == DailyWorkReport.STATUS_SUBMITTED:
        return True
    return bool(report.draft_saved_at)


def weekly_report_visible_to_team(report) -> bool:
    if report is None:
        return False
    if report.status == WeeklyWorkReport.STATUS_SUBMITTED:
        return True
    return bool(report.draft_saved_at)


def build_team_office_report_map(
    team_ids,
    report_date,
    report_period: str,
) -> dict[int, DailyWorkReport]:
    """
    Báo cáo VP theo chu kỳ tab quản lý.
    Tab Ngày: ưu tiên báo cáo ngày; nếu chưa có thì hiển thị báo cáo tuần của tuần chứa ngày đó
    (MKT và các phòng nộp báo tuần vẫn thấy trên tab Ngày).
    """
    if not team_ids:
        return {}

    base = meaningful_daily_reports_qs().filter(
        employee_id__in=team_ids,
        report_profile=REPORT_PROFILE_OFFICE,
    )

    if report_period == PERIOD_MONTH:
        anchor = report_date.replace(day=1)
        reports = base.filter(report_period=PERIOD_MONTH, report_date=anchor)
        return {r.employee_id: r for r in reports}

    if report_period == PERIOD_WEEK:
        anchor = monday_of(report_date)
        reports = base.filter(report_period=PERIOD_WEEK, report_date=anchor)
        return {r.employee_id: r for r in reports}

    week_anchor = monday_of(report_date)
    report_map: dict[int, DailyWorkReport] = {}
    for report in base.filter(report_period=PERIOD_WEEK, report_date=week_anchor):
        report_map[report.employee_id] = report
    for report in base.filter(report_period=PERIOD_DAY, report_date=report_date):
        report_map[report.employee_id] = report
    return report_map


def _active_subordinate_qs(m2m_manager):
    return m2m_manager.filter(is_active=True, profile__is_employed=True)


def build_report_team_department_groups(viewer, team_users, *, dept_filter: str = ''):
    """
    Nhóm cấp dưới theo phòng ban — từ vị trí chính và từng slot kiêm nhiệm.
    Trả về list[{key, label, subtitle, sort_order, members: [User, ...]}].
    """
    profile = get_profile(viewer)
    if not profile:
        return []

    team_ids = set(team_users.values_list('pk', flat=True))
    if not team_ids:
        return []

    user_by_id = {u.pk: u for u in team_users}
    assignment: dict[int, str] = {}
    groups_meta: list[dict] = []

    if profile.department_id:
        primary_label = profile.department.name
        primary_sort = profile.department.sort_order
    else:
        primary_label = 'Vị trí chính'
        primary_sort = 0
    primary_key = f'primary-{profile.department_id or 0}'
    primary_sub_ids = set(
        _active_subordinate_qs(profile.subordinates).values_list('pk', flat=True),
    ) & team_ids
    if primary_sub_ids:
        subtitle = profile.job_position or profile.get_role_display()
        groups_meta.append({
            'key': primary_key,
            'department_id': profile.department_id,
            'label': primary_label,
            'subtitle': subtitle,
            'sort_order': (primary_sort, 0),
            'member_ids': primary_sub_ids,
        })
        for uid in primary_sub_ids:
            if uid not in assignment:
                assignment[uid] = primary_key

    for slot in get_active_concurrent_positions(profile):
        if slot.role not in MANAGER_SLOT_ROLES:
            continue
        slot_sub_ids = set(
            _active_subordinate_qs(slot.subordinates).values_list('pk', flat=True),
        ) & team_ids
        if not slot_sub_ids:
            continue
        dept = slot.department
        slot_key = f'slot-{slot.pk}'
        label = dept.name if dept else 'Kiêm nhiệm'
        sort_order = (dept.sort_order if dept else 9999, slot.sort_order)
        subtitle_parts = []
        if slot.division_id:
            subtitle_parts.append(slot.division.name)
        if slot.job_position:
            subtitle_parts.append(slot.job_position)
        groups_meta.append({
            'key': slot_key,
            'department_id': slot.department_id,
            'label': label,
            'subtitle': ' · '.join(subtitle_parts),
            'sort_order': sort_order,
            'member_ids': slot_sub_ids,
        })
        for uid in slot_sub_ids:
            if uid not in assignment:
                assignment[uid] = slot_key

    orphan_ids = team_ids - set(assignment.keys())
    if orphan_ids:
        groups_meta.append({
            'key': 'other',
            'department_id': None,
            'label': 'Khác',
            'subtitle': '',
            'sort_order': (99999, 0),
            'member_ids': orphan_ids,
        })
        for uid in orphan_ids:
            assignment[uid] = 'other'

    groups_meta.sort(key=lambda g: g['sort_order'])

    if dept_filter:
        groups_meta = [g for g in groups_meta if g['key'] == dept_filter]

    result = []
    for group in groups_meta:
        member_ids = {
            uid for uid in group['member_ids']
            if assignment.get(uid) == group['key'] and uid in user_by_id
        }
        members = sorted(
            [user_by_id[uid] for uid in member_ids],
            key=lambda u: (
                (getattr(getattr(u, 'profile', None), 'full_name', '') or u.username).lower(),
                u.username.lower(),
            ),
        )
        if members:
            result.append({
                'key': group['key'],
                'department_id': group['department_id'],
                'label': group['label'],
                'subtitle': group['subtitle'],
                'members': members,
            })
    return result


def department_filter_choices(department_groups):
    """Danh sách phòng ban cho dropdown lọc."""
    return [{'key': g['key'], 'label': g['label']} for g in department_groups]
