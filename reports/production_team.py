"""Team view — báo cáo sản xuất theo ca."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Exists, IntegerField, OuterRef, Subquery, Sum, Value, DecimalField
from django.db.models.functions import Coalesce

from hrm.permissions import (
    ROLE_DEPARTMENT_HEAD,
    ROLE_DIRECTOR,
    ROLE_DIVISION_HEAD,
    ROLE_TEAM_LEADER,
)
from reports.models import (
    DailyWorkReport,
    ProductionHourlyQuantity,
    ProductionShiftProduct,
    ReportComment,
)
from reports.period_utils import PERIOD_DAY
from reports.production_shift_policy import (
    PRODUCTION_SHIFT_ORDER,
    production_reports_for_day,
    shift_badge_class,
    shift_display_label,
)
from reports.report_profile import REPORT_PROFILE_PRODUCTION
from reports.production_hourly import (
    _combined_efficiency_pct,
    _products_for_productivity,
    _report_efficiency_totals,
    _report_overall_efficiency_pct,
    compute_day_work_waste_summary,
    list_production_products,
    report_has_manager_fixable_anomaly,
)
from reports.team_utils import (
    build_profile_department_groups,
    build_report_team_department_groups,
    daily_report_visible_to_team,
    department_filter_choices,
    meaningful_daily_reports_qs,
)
from reports.week_utils import monday_of

PRODUCTION_WEEK_WORK_DAYS = 6  # Thứ 2 – Thứ 7

# Tổ trưởng trở lên — không bắt buộc BC SX, không hiện «Chưa báo cáo».
PRODUCTION_NO_REPORT_EXEMPT_ROLES = frozenset({
    ROLE_TEAM_LEADER,
    ROLE_DIVISION_HEAD,
    ROLE_DEPARTMENT_HEAD,
    ROLE_DIRECTOR,
})


def is_production_no_report_exempt(user) -> bool:
    """Vai trò từ Tổ trưởng trở lên — bỏ dòng «Chưa báo cáo» trên team SX."""
    from hrm.concurrent_positions import effective_roles

    return bool(effective_roles(user) & PRODUCTION_NO_REPORT_EXEMPT_ROLES)


def production_no_report_exempt_ids(users) -> set[int]:
    return {user.pk for user in users if is_production_no_report_exempt(user)}


def build_production_reports_by_employee(reports_qs) -> dict[int, list[DailyWorkReport]]:
    by_employee: dict[int, list[DailyWorkReport]] = defaultdict(list)
    for report in reports_qs:
        by_employee[report.employee_id].append(report)
    return dict(by_employee)


def _visible_reports(reports: list[DailyWorkReport], visible_fn) -> list[DailyWorkReport]:
    return [report for report in reports if _visible_report(report, visible_fn)]


def _shift_badges_for_reports(reports: list[DailyWorkReport]) -> list[dict]:
    badges: list[dict] = []
    shifts_present = {report.shift for report in reports}
    for shift in PRODUCTION_SHIFT_ORDER:
        if shift in shifts_present:
            badges.append({
                'shift': shift,
                'label': shift_display_label(shift),
                'badge_class': shift_badge_class(shift),
            })
    return badges


def _sort_visible_production_reports(reports: list[DailyWorkReport]) -> list[DailyWorkReport]:
    reports = list(reports)
    reports.sort(
        key=lambda report: (
            PRODUCTION_SHIFT_ORDER.index(report.shift)
            if report.shift in PRODUCTION_SHIFT_ORDER
            else len(PRODUCTION_SHIFT_ORDER)
        )
    )
    return reports


def _production_row_flags(visible: list[DailyWorkReport]) -> dict:
    """Cờ trạng thái / tóm tắt — không tính hiệu suất (dùng cho đếm thống kê)."""
    from reports.report_lock import is_production_approve_overdue

    total_qty = sum(int(getattr(report, 'total_qty', 0) or 0) for report in visible)
    total_damaged = sum(int(getattr(report, 'total_damaged', 0) or 0) for report in visible)
    primary = visible[0] if visible else None
    return {
        'report': primary,
        'production_reports': visible,
        'production_report_count': len(visible),
        'production_total_qty': total_qty,
        'production_total_damaged': total_damaged,
        'production_all_submitted': bool(visible) and all(
            report.status == DailyWorkReport.STATUS_SUBMITTED for report in visible
        ),
        'production_any_submitted': any(
            report.status == DailyWorkReport.STATUS_SUBMITTED for report in visible
        ),
        'production_all_reviewed': bool(visible) and all(report.hod_reviewed for report in visible),
        'production_any_rejected': bool(visible) and any(
            getattr(report, 'hod_rejected', False) and not report.hod_reviewed
            for report in visible
        ),
        'production_any_approve_overdue': any(
            report.status == DailyWorkReport.STATUS_SUBMITTED
            and not report.hod_reviewed
            and not getattr(report, 'hod_rejected', False)
            and is_production_approve_overdue(report)
            for report in visible
        ),
        'production_has_manager_comment': any(
            getattr(report, 'has_manager_comment', False) for report in visible
        ),
        'production_has_employee_reply': any(
            getattr(report, 'has_employee_reply', False) for report in visible
        ),
        'production_has_anomaly': any(
            report.status != DailyWorkReport.STATUS_SUBMITTED
            and report_has_manager_fixable_anomaly(report)
            for report in visible
        ),
        'production_any_auto_submitted': any(
            report.status == DailyWorkReport.STATUS_SUBMITTED
            and getattr(report, 'auto_submitted', False)
            for report in visible
        ),
        'production_all_auto_submitted': bool(visible) and all(
            report.status == DailyWorkReport.STATUS_SUBMITTED
            and getattr(report, 'auto_submitted', False)
            for report in visible
        ),
        'shift_badges': _shift_badges_for_reports(visible),
    }


def _aggregate_production_row(
    reports: list[DailyWorkReport],
    visible_fn,
    *,
    compute_efficiency: bool = True,
) -> dict:
    visible = _sort_visible_production_reports(_visible_reports(reports, visible_fn))
    row = _production_row_flags(visible)
    row['production_efficiency_pct'] = (
        _weighted_efficiency_pct(visible) if compute_efficiency and visible else None
    )
    return row


def _visible_report(report, visible_fn) -> DailyWorkReport | None:
    if report and visible_fn(report):
        return report
    return None


def _reports_by_employee_date(
    reports: list[DailyWorkReport],
) -> dict[date, list[DailyWorkReport]]:
    by_date: dict[date, list[DailyWorkReport]] = defaultdict(list)
    for report in reports:
        by_date[report.report_date].append(report)
    return dict(by_date)


def _iter_dates(date_from: date, date_to: date):
    day = date_from
    while day <= date_to:
        yield day
        day += timedelta(days=1)


def _append_production_member_rows(
    rows: list[dict],
    member,
    reports: list[DailyWorkReport],
    visible_fn,
    *,
    date_from: date,
    date_to: date,
    status_filter: str = '',
) -> None:
    by_date = _reports_by_employee_date(reports)
    skip_empty = is_production_no_report_exempt(member)
    # Khi đang lọc trạng thái có BC (đã nộp/duyệt…), bỏ ngày trống — tránh dựng rồi lọc lại.
    only_days_with_reports = status_filter in {
        'submitted',
        'missing',
        'reviewed',
        'rejected',
        'not_reviewed',
    }
    if by_date:
        day_iter = (
            sorted(by_date.keys(), reverse=True)
            if only_days_with_reports
            else sorted(_iter_dates(date_from, date_to), reverse=True)
        )
        for report_date in day_iter:
            day_reports = by_date.get(report_date, [])
            if only_days_with_reports and not day_reports:
                continue
            agg = _aggregate_production_row(day_reports, visible_fn)
            if skip_empty and not agg['production_report_count']:
                continue
            rows.append({
                'member': member,
                'report_date': report_date,
                **agg,
            })
        return
    if skip_empty or only_days_with_reports:
        return
    rows.append({
        'member': member,
        'report_date': None,
        **_aggregate_production_row([], visible_fn),
    })


def _ensure_team_members_in_groups(groups: list[dict], team) -> list[dict]:
    """Đảm bảo mọi NV trong queryset team đều có trong một nhóm hiển thị."""
    team_users = list(team.select_related('profile', 'profile__department'))
    if not team_users:
        return groups

    indexed = {user.pk: user for user in team_users}
    covered = {member.pk for group in groups for member in group['members']}
    missing = [indexed[pk] for pk in indexed if pk not in covered]
    if not missing:
        return groups

    groups = [dict(group, members=list(group['members'])) for group in groups]
    other = next((group for group in groups if group['key'] == 'other'), None)
    if other is None:
        groups.append({
            'key': 'other',
            'department_id': None,
            'label': 'Khác',
            'subtitle': '',
            'members': missing,
        })
    else:
        other['members'] = sorted(
            {member.pk: member for member in other['members'] + missing}.values(),
            key=lambda user: (
                (getattr(getattr(user, 'profile', None), 'full_name', '') or user.username).lower(),
                user.username.lower(),
            ),
        )
    return groups


def build_production_team_department_groups(
    viewer,
    team,
    reports_by_employee: dict[int, list[DailyWorkReport]],
    visible_fn,
    *,
    date_from: date,
    date_to: date,
    dept_filter: str = '',
    status_filter: str = '',
):
    all_groups = build_report_team_department_groups(viewer, team)
    dept_choices = department_filter_choices(all_groups)
    groups = (
        build_report_team_department_groups(viewer, team, dept_filter=dept_filter)
        if dept_filter else all_groups
    )
    groups = _ensure_team_members_in_groups(groups, team)
    department_groups = []
    for group in groups:
        rows = []
        for member in group['members']:
            reports = reports_by_employee.get(member.id, [])
            _append_production_member_rows(
                rows,
                member,
                reports,
                visible_fn,
                date_from=date_from,
                date_to=date_to,
                status_filter=status_filter,
            )
        department_groups.append({**group, 'rows': rows})
    return department_groups, dept_choices


def production_team_submitted_count(
    reports_by_employee: dict[int, list[DailyWorkReport]],
    visible_fn,
    *,
    team_count: int,
) -> tuple[int, int]:
    submitted = 0
    for reports in reports_by_employee.values():
        agg = _aggregate_production_row(reports, visible_fn, compute_efficiency=False)
        if agg['production_any_submitted']:
            submitted += 1
    missing = team_count - submitted
    return submitted, missing


def production_team_status_counts(
    team_ids: list[int],
    reports_by_employee: dict[int, list[DailyWorkReport]],
    visible_fn,
    *,
    exempt_no_report_ids: set[int] | None = None,
) -> dict[str, int]:
    """Đếm theo NV trong khoảng lọc: đã nộp / chưa nộp (có BC) / chưa báo cáo."""
    exempt = exempt_no_report_ids or set()
    submitted = 0
    unsubmitted_report = 0
    no_report = 0
    for emp_id in team_ids:
        reports = reports_by_employee.get(emp_id, [])
        agg = _aggregate_production_row(reports, visible_fn, compute_efficiency=False)
        if agg['production_any_submitted']:
            submitted += 1
        elif agg['production_report_count'] > 0:
            unsubmitted_report += 1
        elif emp_id not in exempt:
            no_report += 1
    return {
        'submitted': submitted,
        'unsubmitted_report': unsubmitted_report,
        'no_report': no_report,
    }


def production_team_row_is_submitted(row, *, submitted_status: str, shift_filter: str = '') -> bool:
    reports = row.get('production_reports') or []
    if not reports and row.get('report'):
        reports = [row['report']]
    return any(report.status == submitted_status for report in reports)


def production_team_row_matches_filter(
    row,
    status_filter: str,
    *,
    submitted_status: str,
) -> bool:
    """Lọc dòng SX — «Chưa nộp» = đã có BC nhưng chưa gửi; «Chưa báo cáo» = chưa có BC."""
    if status_filter == 'submitted':
        return production_team_row_is_submitted(row, submitted_status=submitted_status)
    if status_filter == 'missing':
        return (
            row.get('production_report_count', 0) > 0
            and not production_team_row_is_submitted(row, submitted_status=submitted_status)
        )
    if status_filter == 'no_report':
        return row.get('production_report_count', 0) == 0
    if status_filter == 'reviewed':
        return (
            row.get('production_report_count', 0) > 0
            and row.get('production_any_submitted', False)
            and row.get('production_all_reviewed', False)
        )
    if status_filter == 'rejected':
        return bool(row.get('production_any_rejected', False))
    if status_filter == 'not_reviewed':
        return (
            row.get('production_any_submitted', False)
            and not row.get('production_any_rejected', False)
            and not row.get('production_all_reviewed', False)
        )
    return True


def production_team_review_row_counts(department_groups: list[dict]) -> dict[str, int]:
    """Đếm dòng NV×ngày đã duyệt / chưa duyệt (trong khoảng lọc)."""
    reviewed = 0
    not_reviewed = 0
    rejected = 0
    for group in department_groups:
        for row in group.get('rows') or []:
            if row.get('production_any_rejected'):
                rejected += 1
            elif row.get('production_any_submitted') and row.get('production_all_reviewed'):
                reviewed += 1
            elif row.get('production_any_submitted') and not row.get('production_all_reviewed'):
                not_reviewed += 1
    return {'reviewed': reviewed, 'not_reviewed': not_reviewed, 'rejected': rejected}


def expected_morning_days_through(anchor: date) -> int:
    week_start = monday_of(anchor)
    count = 0
    for offset in range(PRODUCTION_WEEK_WORK_DAYS):
        day = week_start + timedelta(days=offset)
        if day > anchor:
            break
        count += 1
    return count


def build_production_week_rollup(
    team_ids: list[int],
    anchor_date: date,
    visible_fn,
) -> dict[int, dict]:
    if not team_ids:
        return {}

    week_start = monday_of(anchor_date)
    week_end = week_start + timedelta(days=PRODUCTION_WEEK_WORK_DAYS - 1)
    submitted_dates: dict[int, set[date]] = defaultdict(set)
    reports = meaningful_daily_reports_qs().filter(
        employee_id__in=team_ids,
        report_date__gte=week_start,
        report_date__lte=week_end,
        report_profile=REPORT_PROFILE_PRODUCTION,
        report_period=PERIOD_DAY,
        shift=DailyWorkReport.SHIFT_MORNING,
        status=DailyWorkReport.STATUS_SUBMITTED,
    )
    for report in reports:
        if visible_fn(report):
            submitted_dates[report.employee_id].add(report.report_date)

    expected = expected_morning_days_through(anchor_date)
    rollup = {}
    for employee_id in team_ids:
        done = len(submitted_dates.get(employee_id, set()))
        missing = max(0, expected - done)
        rollup[employee_id] = {
            'submitted_days': done,
            'expected_days': expected,
            'missing_days': missing,
            'is_complete': missing == 0,
            'warning': (
                f'Thiếu {missing} ngày ca sáng tuần này'
                if missing > 0 and expected > 0 else ''
            ),
        }
    return rollup


def build_production_day_shift_tabs(
    report: DailyWorkReport,
    *,
    detail_url_name: str,
    list_query: str = '',
) -> list[dict]:
    """Tab chuyển ca trong trang chi tiết — cùng NV + ngày."""
    from django.urls import reverse

    if not report.is_production_report:
        return []

    siblings = list(production_reports_for_day(report.employee, report.report_date))
    siblings.sort(
        key=lambda row: (
            PRODUCTION_SHIFT_ORDER.index(row.shift)
            if row.shift in PRODUCTION_SHIFT_ORDER
            else len(PRODUCTION_SHIFT_ORDER)
        )
    )
    if len(siblings) <= 1:
        return []

    tabs = []
    for sibling in siblings:
        url = reverse(detail_url_name, args=[sibling.pk])
        if list_query:
            url = f'{url}?{list_query}'
        tabs.append({
            'pk': sibling.pk,
            'shift': sibling.shift,
            'label': shift_display_label(sibling.shift),
            'badge_class': shift_badge_class(sibling.shift),
            'is_active': sibling.pk == report.pk,
            'url': url,
        })
    return tabs


def _filter_reports_by_shift(
    reports: list[DailyWorkReport],
    shift_filter: str,
) -> list[DailyWorkReport]:
    if not shift_filter:
        return reports
    from reports.production_slots import normalize_shift

    target = normalize_shift(shift_filter)
    return [
        report
        for report in reports
        if normalize_shift(report.shift or DailyWorkReport.SHIFT_MORNING) == target
    ]


def build_production_summary_shift_filter_choices() -> list[dict]:
    """Bộ lọc ca trên form tổng hợp / thống kê SX — mặc định Tất cả ca."""
    choices = [{'key': 'ALL', 'label': 'Tất cả ca'}]
    for shift in PRODUCTION_SHIFT_ORDER:
        choices.append({'key': shift, 'label': shift_display_label(shift)})
    return choices


def build_production_summary_shift_tabs(
    *,
    active_shift: str,
    base_params: dict[str, str],
    url_name: str = 'reports:team_summary_cn',
) -> list[dict]:
    """Deprecated — giữ tương thích; UI đã chuyển sang bộ lọc select."""
    from urllib.parse import urlencode

    from django.urls import reverse

    tabs = []
    all_params = {k: v for k, v in base_params.items() if k != 'shift'}
    tabs.append({
        'shift': 'all',
        'label': 'Tất cả ca',
        'badge_class': 'badge bg-secondary-subtle text-secondary',
        'is_active': not active_shift,
        'url': f"{reverse(url_name)}?{urlencode(all_params)}" if all_params else reverse(url_name),
    })
    for shift in PRODUCTION_SHIFT_ORDER:
        params = {**all_params, 'shift': shift}
        tabs.append({
            'shift': shift,
            'label': shift_display_label(shift),
            'badge_class': shift_badge_class(shift),
            'is_active': shift == active_shift,
            'url': f"{reverse(url_name)}?{urlencode(params)}",
        })
    return tabs


SUMMARY_METRIC_EFFICIENCY = 'efficiency'
SUMMARY_METRIC_TIME = 'time'
SUMMARY_METRIC_QUANTITY = 'quantity'
SUMMARY_METRIC_CHOICES = (
    (SUMMARY_METRIC_EFFICIENCY, 'Hiệu suất TB'),
    (SUMMARY_METRIC_TIME, 'Hiệu suất theo thời gian'),
    (SUMMARY_METRIC_QUANTITY, 'Sản lượng'),
)
SUMMARY_METRIC_KEYS = frozenset(key for key, _label in SUMMARY_METRIC_CHOICES)

SUMMARY_DISPLAY_ALL = 'all'
SUMMARY_DISPLAY_DAYS_WITH_REPORT = 'days_with_report'
SUMMARY_DISPLAY_CHOICES = (
    (SUMMARY_DISPLAY_ALL, 'Tất cả nhân viên'),
    (SUMMARY_DISPLAY_DAYS_WITH_REPORT, 'Chỉ ngày có báo cáo'),
)
SUMMARY_DISPLAY_KEYS = frozenset(key for key, _label in SUMMARY_DISPLAY_CHOICES)


def normalize_summary_metric(raw: str | None) -> str:
    key = (raw or SUMMARY_METRIC_EFFICIENCY).strip().lower()
    if key in SUMMARY_METRIC_KEYS:
        return key
    return SUMMARY_METRIC_EFFICIENCY


def normalize_summary_display(raw: str | None) -> str:
    key = (raw or SUMMARY_DISPLAY_ALL).strip().lower().replace('-', '_')
    aliases = {
        'days': SUMMARY_DISPLAY_DAYS_WITH_REPORT,
        'reported_days': SUMMARY_DISPLAY_DAYS_WITH_REPORT,
        'with_report_days': SUMMARY_DISPLAY_DAYS_WITH_REPORT,
        'with_report': SUMMARY_DISPLAY_DAYS_WITH_REPORT,
        'co_bao_cao': SUMMARY_DISPLAY_DAYS_WITH_REPORT,
    }
    key = aliases.get(key, key)
    if key in SUMMARY_DISPLAY_KEYS:
        return key
    return SUMMARY_DISPLAY_ALL


def build_production_summary_display_choices() -> list[dict]:
    return [{'key': key, 'label': label} for key, label in SUMMARY_DISPLAY_CHOICES]


def build_production_summary_metric_tabs(
    *,
    active_metric: str,
    base_params: dict[str, str],
    url_name: str = 'reports:report_stats_cn',
) -> list[dict]:
    """Tab chọn chỉ số: hiệu suất / hiệu suất thời gian / sản lượng."""
    from urllib.parse import urlencode

    from django.urls import reverse

    tabs = []
    for key, label in SUMMARY_METRIC_CHOICES:
        params = {**base_params, 'metric': key}
        tabs.append({
            'key': key,
            'label': label,
            'is_active': key == active_metric,
            'url': f"{reverse(url_name)}?{urlencode(params)}",
        })
    return tabs


def _iter_summary_members(summary: dict):
    sections = summary.get('shift_sections') or []
    if sections:
        for section in sections:
            for group in section.get('groups') or []:
                for member in group.get('members') or []:
                    yield member
        return
    for group in summary.get('groups') or []:
        for member in group.get('members') or []:
            yield member


def _member_has_report_data(member: dict) -> bool:
    """True khi ma trận hiện ít nhất một ô có số liệu (không phải dòng toàn —)."""
    if any(cell.get('has_data') for cell in (member.get('cells') or [])):
        return True
    # avg_value chỉ khi đã cộng được metric từ ô có dữ liệu
    return member.get('avg_value') is not None


def _filter_summary_groups_keep_reported(groups: list[dict]) -> tuple[list[dict], int]:
    """Giữ NV đã nộp BC trong kỳ; bỏ dòng trống; đánh lại STT theo section/nhóm."""
    out = []
    stt = 0
    for group in groups or []:
        kept = []
        for member in group.get('members') or []:
            if not _member_has_report_data(member):
                continue
            stt += 1
            kept.append({**member, 'stt': stt})
        if kept:
            out.append({**group, 'members': kept})
    return out, stt


def _apply_summary_display_mode(summary: dict, display_mode: str) -> dict:
    """Lọc hiển thị ma trận.

    days_with_report: trong kỳ lọc, chỉ giữ nhân viên đã gửi BC
    (bỏ dòng trống toàn —); giữ nguyên các cột ngày.
    """
    display_mode = normalize_summary_display(display_mode)
    summary['display_mode'] = display_mode
    summary['display_label'] = dict(SUMMARY_DISPLAY_CHOICES).get(
        display_mode, 'Tất cả nhân viên'
    )
    summary['display_filter_choices'] = build_production_summary_display_choices()
    if display_mode != SUMMARY_DISPLAY_DAYS_WITH_REPORT:
        return summary

    sections = summary.get('shift_sections') or []
    if sections:
        new_sections = []
        total_members = 0
        with_data_ids: set[int] = set()
        for section in sections:
            filtered_groups, stt = _filter_summary_groups_keep_reported(
                section.get('groups') or []
            )
            if not filtered_groups:
                continue
            for group in filtered_groups:
                for row in group['members']:
                    member = row.get('member')
                    if member is not None:
                        with_data_ids.add(member.pk)
            new_sections.append({
                **section,
                'groups': filtered_groups,
                'member_count': stt,
            })
            total_members += stt
        summary['shift_sections'] = new_sections
        summary['groups'] = [
            g for section in new_sections for g in section.get('groups') or []
        ]
        summary['member_count'] = total_members
        summary['members_with_data'] = len(with_data_ids)
        summary['has_members'] = total_members > 0
        return summary

    filtered_groups, stt = _filter_summary_groups_keep_reported(
        summary.get('groups') or []
    )
    summary['groups'] = filtered_groups
    summary['member_count'] = stt
    summary['members_with_data'] = stt
    summary['has_members'] = stt > 0
    return summary


def _production_total_qty_subquery():
    return (
        ProductionHourlyQuantity.objects.filter(product__report_id=OuterRef('pk'))
        .values('product__report_id')
        .annotate(total=Sum('quantity'))
        .values('total')[:1]
    )


def _production_total_damaged_subquery():
    return (
        ProductionShiftProduct.objects.filter(report_id=OuterRef('pk'))
        .values('report_id')
        .annotate(total=Sum('total_damaged_quantity'))
        .values('total')[:1]
    )


# =========================================================
# BÁO CÁO TỔNG HỢP — ma trận hiệu suất theo NV × ngày
# =========================================================

WEEKDAY_LABELS_VI = ('Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'CN')


def _weekday_label_vi(day: date) -> str:
    return WEEKDAY_LABELS_VI[day.weekday()]


def _efficiency_totals_for_reports(
    reports,
) -> tuple[Decimal, Decimal, Decimal]:
    """Tổng SL / giờ / SL kỳ vọng trên một hoặc nhiều báo cáo ca."""
    total_qty = Decimal('0')
    total_hours = Decimal('0')
    total_expected = Decimal('0')
    for report in reports:
        qty, hours, expected = _report_efficiency_totals(
            list_production_products(report),
        )
        total_qty += qty
        total_hours += hours
        total_expected += expected
    return total_qty, total_hours, total_expected


def _combined_efficiency_parts(reports) -> tuple[Decimal, Decimal]:
    """Trả (HS TB × trọng số giờ, tổng giờ) — HS TB = HS sản lượng × HS thời gian."""
    weighted = Decimal('0')
    weight = Decimal('0')
    for report in reports:
        products = list_production_products(report)
        productive = _products_for_productivity(products)
        qty, hours, expected = _report_efficiency_totals(productive)
        quantity_pct = (
            float((qty / expected * 100).quantize(Decimal('0.01')))
            if expected > 0 and hours > 0
            else None
        )
        day_times = compute_day_work_waste_summary(report, products)
        combined = _combined_efficiency_pct(
            quantity_pct,
            day_times.get('time_efficiency_pct'),
        )
        if combined is None:
            continue
        part_weight = hours if hours > 0 else Decimal('1')
        weighted += Decimal(str(combined)) * part_weight
        weight += part_weight
    return weighted, weight


def _time_efficiency_parts(reports) -> tuple[Decimal, Decimal]:
    """Trả (HS thời gian × trọng số giờ khai báo, tổng trọng số)."""
    weighted = Decimal('0')
    weight = Decimal('0')
    for report in reports:
        day_times = compute_day_work_waste_summary(
            report,
            list_production_products(report),
        )
        pct = day_times.get('time_efficiency_pct')
        if pct is None:
            continue
        declared = getattr(report, 'declared_work_hours', None)
        part_weight = (
            Decimal(str(declared))
            if declared is not None and declared > 0
            else Decimal('1')
        )
        weighted += Decimal(str(pct)) * part_weight
        weight += part_weight
    return weighted, weight


def _quantity_total(reports) -> Decimal:
    total_qty, _hours, _expected = _efficiency_totals_for_reports(reports)
    return total_qty


def _pct_from_parts(weighted: Decimal, hours: Decimal) -> float | None:
    if hours > 0:
        return float((weighted / hours).quantize(Decimal('0.01')))
    return None


def _weighted_efficiency_pct(reports: list[DailyWorkReport]) -> float | None:
    """Hiệu suất TB — HS sản lượng × HS thời gian (trọng số theo giờ công đoạn)."""
    return _pct_from_parts(*_combined_efficiency_parts(reports))


def report_overall_efficiency_pct(report) -> float | None:
    """Hiệu suất TB 1 báo cáo — khớp day_summary.avg_efficiency_pct."""
    products = list_production_products(report)
    quantity_pct = _report_overall_efficiency_pct(_products_for_productivity(products))
    day_times = compute_day_work_waste_summary(report, products)
    return _combined_efficiency_pct(quantity_pct, day_times.get('time_efficiency_pct'))


def _day_efficiency_pct(reports: list[DailyWorkReport]) -> float | None:
    """Hiệu suất trung bình trong ngày — HS sản lượng × HS thời gian."""
    return _weighted_efficiency_pct(reports)


def _metric_parts(reports, metric: str) -> tuple[Decimal, Decimal]:
    """Trả (tử số tích lũy, mẫu số) theo loại chỉ số."""
    if metric == SUMMARY_METRIC_TIME:
        return _time_efficiency_parts(reports)
    if metric == SUMMARY_METRIC_QUANTITY:
        qty = _quantity_total(reports)
        return qty, (Decimal('1') if qty > 0 else Decimal('0'))
    return _combined_efficiency_parts(reports)


def _metric_value_from_parts(numerator: Decimal, denominator: Decimal, metric: str) -> float | None:
    if metric == SUMMARY_METRIC_QUANTITY:
        if denominator > 0:
            return float(numerator.quantize(Decimal('0.01')))
        return None
    return _pct_from_parts(numerator, denominator)


def _build_summary_member_row(
    member,
    shift_reports: list[DailyWorkReport],
    *,
    days: list[dict],
    metric: str,
    is_quantity: bool,
    stt: int,
    shift: str,
    day_totals: list[dict],
) -> tuple[dict, Decimal, Decimal]:
    """Một dòng NV×ca; cập nhật day_totals; trả (row, numerator, denominator)."""
    by_date = _reports_by_employee_date(shift_reports)
    cells = []
    member_numerator = Decimal('0')
    member_denominator = Decimal('0')
    for idx, day in enumerate(days):
        day_reports = by_date.get(day['date'], [])
        numerator, denominator = _metric_parts(day_reports, metric)
        value = _metric_value_from_parts(numerator, denominator, metric)
        primary_report = day_reports[0] if day_reports else None
        cells.append({
            'value': value,
            'efficiency_pct': value if not is_quantity else None,
            'has_data': value is not None,
            'is_weekend': day['is_weekend'],
            'report_pk': primary_report.pk if primary_report else None,
        })
        if denominator > 0:
            day_totals[idx]['numerator'] += numerator
            day_totals[idx]['denominator'] += denominator
            member_numerator += numerator
            member_denominator += denominator
    avg = _metric_value_from_parts(member_numerator, member_denominator, metric)
    profile = getattr(member, 'profile', None)
    display_name = (
        profile.full_name if profile and profile.full_name else member.username
    )
    row = {
        'stt': stt,
        'member': member,
        'name': display_name.upper(),
        'division': (
            profile.division.name
            if profile and getattr(profile, 'division_id', None)
            else ''
        ),
        'shift': shift,
        'shift_label': shift_display_label(shift),
        'show_identity': True,
        'cells': cells,
        'avg_value': avg,
        'avg_efficiency_pct': avg if not is_quantity else None,
        'report_count': len(shift_reports),
    }
    return row, member_numerator, member_denominator


def _build_summary_groups_for_shift(
    groups_src: list[dict],
    reports_by_employee: dict[int, list[DailyWorkReport]],
    visible_fn,
    *,
    shift: str,
    days: list[dict],
    metric: str,
    is_quantity: bool,
    day_totals: list[dict],
    only_with_shift_reports: bool = False,
) -> tuple[list[dict], int, int, Decimal, Decimal]:
    """Nhóm phòng ban cho một ca. Trả groups, member_count, with_data, grand_num, grand_den."""
    stt = 0
    members_with_data = 0
    grand_numerator = Decimal('0')
    grand_denominator = Decimal('0')
    groups = []
    for group in groups_src:
        members_out = []
        for member in group['members']:
            visible = _visible_reports(reports_by_employee.get(member.id, []), visible_fn)
            shift_reports = _filter_reports_by_shift(visible, shift)
            if only_with_shift_reports and not shift_reports:
                continue
            stt += 1
            row, num, den = _build_summary_member_row(
                member,
                shift_reports,
                days=days,
                metric=metric,
                is_quantity=is_quantity,
                stt=stt,
                shift=shift,
                day_totals=day_totals,
            )
            if row['avg_value'] is not None:
                members_with_data += 1
            grand_numerator += num
            grand_denominator += den
            members_out.append(row)
        if members_out:
            groups.append({**group, 'label': group['label'], 'members': members_out})
    return groups, stt, members_with_data, grand_numerator, grand_denominator


def build_production_team_summary(
    viewer,
    team,
    reports_by_employee: dict[int, list[DailyWorkReport]],
    visible_fn,
    *,
    date_from: date,
    date_to: date,
    dept_filter: str = '',
    shift_filter: str = '',
    metric: str = SUMMARY_METRIC_EFFICIENCY,
    display_mode: str = SUMMARY_DISPLAY_ALL,
) -> dict:
    """Ma trận NV × ngày theo metric.

    - Tất cả nhân viên: ca sáng + ca tối đều danh sách đầy đủ (ô trống nếu chưa nộp).
    - Chỉ ngày có báo cáo: chỉ NV có số liệu trong kỳ; ca tối chỉ những người đã có BC ca tối
      (khối ca tối ẩn nếu không ai có dữ liệu).
    - Tất cả ca: khối Ca sáng trên, Ca tối dưới.
    """
    metric = normalize_summary_metric(metric)
    display_mode = normalize_summary_display(display_mode)
    is_quantity = metric == SUMMARY_METRIC_QUANTITY
    metric_label = dict(SUMMARY_METRIC_CHOICES).get(metric, 'Hiệu suất')
    split_by_shift = not shift_filter
    shift_label = shift_display_label(shift_filter) if shift_filter else 'Tất cả ca'
    # Chỉ khi lọc «Chỉ ngày có báo cáo» mới thu hẹp ca tối xuống NV đã nộp.
    night_only_with_reports = display_mode == SUMMARY_DISPLAY_DAYS_WITH_REPORT

    days = [
        {
            'date': day,
            'weekday': _weekday_label_vi(day),
            'is_weekend': day.weekday() == 6,
        }
        for day in _iter_dates(date_from, date_to)
    ]

    all_groups = build_profile_department_groups(team)
    dept_choices = department_filter_choices(all_groups)
    groups_src = (
        build_profile_department_groups(team, dept_filter=dept_filter)
        if dept_filter else all_groups
    )

    day_totals = [{'numerator': Decimal('0'), 'denominator': Decimal('0')} for _ in days]
    grand_numerator = Decimal('0')
    grand_denominator = Decimal('0')
    members_with_data_ids: set[int] = set()
    shift_sections: list[dict] = []

    if shift_filter:
        only_with = (
            night_only_with_reports
            and shift_filter == DailyWorkReport.SHIFT_NIGHT
        )
        groups, stt, with_data, num, den = _build_summary_groups_for_shift(
            groups_src,
            reports_by_employee,
            visible_fn,
            shift=shift_filter,
            days=days,
            metric=metric,
            is_quantity=is_quantity,
            day_totals=day_totals,
            only_with_shift_reports=only_with,
        )
        grand_numerator += num
        grand_denominator += den
        members_with_data = with_data
        member_count = stt
        shift_sections = [{
            'shift': shift_filter,
            'label': shift_display_label(shift_filter),
            'badge_class': shift_badge_class(shift_filter),
            'groups': groups,
            'member_count': stt,
        }] if groups else []
    else:
        # Ca sáng → ca tối. Tất cả NV: cả hai ca đầy đủ; Chỉ có BC: ca tối chỉ NV đã nộp.
        groups = []
        member_count = 0
        for shift, only_with in (
            (DailyWorkReport.SHIFT_MORNING, False),
            (DailyWorkReport.SHIFT_NIGHT, night_only_with_reports),
        ):
            section_groups, stt, _wd, num, den = _build_summary_groups_for_shift(
                groups_src,
                reports_by_employee,
                visible_fn,
                shift=shift,
                days=days,
                metric=metric,
                is_quantity=is_quantity,
                day_totals=day_totals,
                only_with_shift_reports=only_with,
            )
            if not section_groups:
                continue
            grand_numerator += num
            grand_denominator += den
            for g in section_groups:
                for row in g['members']:
                    if row['avg_value'] is not None:
                        members_with_data_ids.add(row['member'].pk)
                    if shift == DailyWorkReport.SHIFT_MORNING:
                        member_count += 1
            shift_sections.append({
                'shift': shift,
                'label': shift_display_label(shift),
                'badge_class': shift_badge_class(shift),
                'groups': section_groups,
                'member_count': stt,
            })
        # Nhóm phẳng = gộp để tương thích export cũ khi cần
        groups = [
            g
            for section in shift_sections
            for g in section['groups']
        ]
        members_with_data = len(members_with_data_ids)
        if member_count == 0 and shift_sections:
            member_count = sum(s['member_count'] for s in shift_sections)

    day_averages = [
        _metric_value_from_parts(t['numerator'], t['denominator'], metric)
        for t in day_totals
    ]
    for day, avg in zip(days, day_averages):
        day['average'] = avg
    overall_avg = _metric_value_from_parts(grand_numerator, grand_denominator, metric)

    summary = {
        'days': days,
        'groups': groups,
        'shift_sections': shift_sections,
        'dept_choices': dept_choices,
        'has_members': member_count > 0 or any(
            section['member_count'] for section in shift_sections
        ),
        'member_count': member_count,
        'members_with_data': members_with_data,
        'day_averages': day_averages,
        'overall_avg': overall_avg,
        'shift_filter': shift_filter,
        'shift_label': shift_label,
        'split_by_shift': split_by_shift,
        'shift_filter_choices': build_production_summary_shift_filter_choices(),
        'metric': metric,
        'metric_label': metric_label,
        'metric_is_percent': not is_quantity,
        'avg_column_label': 'Tổng' if is_quantity else 'TB',
        'overall_stat_label': (
            'SL toàn team' if is_quantity else f'{metric_label} TB toàn team'
        ),
    }
    return _apply_summary_display_mode(summary, display_mode)


def query_production_team_reports(team_ids, date_from, date_to):
    if not team_ids:
        return DailyWorkReport.objects.none()
    return (
        meaningful_daily_reports_qs()
        .filter(
            employee_id__in=team_ids,
            report_date__gte=date_from,
            report_date__lte=date_to,
            report_profile=REPORT_PROFILE_PRODUCTION,
            report_period=PERIOD_DAY,
        )
        .order_by('-submitted_at', '-report_date', '-id')
        .select_related('employee', 'employee__profile')
        .annotate(
            total_qty=Coalesce(
                Subquery(_production_total_qty_subquery()),
                Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)),
            ),
            total_damaged=Coalesce(
                Subquery(_production_total_damaged_subquery()),
                Value(0, output_field=IntegerField()),
            ),
            has_manager_comment=Exists(
                ReportComment.objects.filter(daily_report=OuterRef('pk')).exclude(author_id=OuterRef('employee_id')),
            ),
            has_employee_reply=Exists(
                ReportComment.objects.filter(daily_report=OuterRef('pk'), author_id=OuterRef('employee_id')),
            ),
        )
        .prefetch_related('production_products__hourly_entries')
    )
