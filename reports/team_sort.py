from __future__ import annotations

from datetime import date, datetime, time
from urllib.parse import urlencode

from django.utils import timezone

from reports.period_utils import PERIOD_DAY, PERIOD_MONTH, PERIOD_WEEK
from reports.production_shift_policy import PRODUCTION_SHIFT_ORDER

TEAM_SORT_MEMBER = 'member'
TEAM_SORT_ANCHOR = 'anchor'
TEAM_SORT_PERIOD = 'period'
TEAM_SORT_STATUS = 'status'
TEAM_SORT_REVIEWED = 'reviewed'
TEAM_SORT_SUMMARY = 'summary'
TEAM_SORT_EFFICIENCY = 'efficiency'

TEAM_SORT_SHIFT = 'shift'

TEAM_SORT_KEYS = frozenset({
    TEAM_SORT_MEMBER,
    TEAM_SORT_ANCHOR,
    TEAM_SORT_PERIOD,
    TEAM_SORT_SHIFT,
    TEAM_SORT_STATUS,
    TEAM_SORT_REVIEWED,
    TEAM_SORT_SUMMARY,
    TEAM_SORT_EFFICIENCY,
})

DEFAULT_TEAM_SORT = TEAM_SORT_ANCHOR

PERIOD_ORDER = {PERIOD_DAY: 1, PERIOD_WEEK: 2, PERIOD_MONTH: 3}
STATUS_ORDER = {None: 0, 'DRAFT': 1, 'SUBMITTED': 2}


def resolve_team_sort(sort_key: str | None, sort_dir: str | None) -> tuple[str, str]:
    key = (sort_key or DEFAULT_TEAM_SORT).strip()
    if key not in TEAM_SORT_KEYS:
        key = DEFAULT_TEAM_SORT
    if sort_dir:
        direction = sort_dir.strip().lower()
        if direction not in ('asc', 'desc'):
            direction = 'asc'
    elif sort_key:
        direction = 'asc'
    else:
        direction = 'desc'
    return key, direction


def team_sort_href(base_params: dict, column_key: str, current_sort: str, current_dir: str) -> str:
    params = {**base_params, 'sort': column_key}
    if current_sort == column_key:
        params['dir'] = 'desc' if current_dir == 'asc' else 'asc'
    else:
        params['dir'] = 'asc'
    return '?' + urlencode(params)


def build_team_table_columns(
    *,
    is_vp: bool,
    is_production: bool = False,
    base_params: dict,
    sort_key: str,
    sort_dir: str,
) -> list[dict]:
    specs = [
        {'key': TEAM_SORT_MEMBER, 'label': 'Nhân viên', 'align': 'start'},
        {
            'key': TEAM_SORT_ANCHOR,
            'label': 'Ngày gửi BC',
            'align': 'start',
            'date_column': True,
        },
        {'key': 'report_anchor', 'label': 'Mốc báo cáo', 'align': 'start', 'office_only': True, 'sortable': False},
        {
            'key': TEAM_SORT_SHIFT,
            'label': 'Ca',
            'align': 'start',
            'production_only': True,
        },
        {'key': TEAM_SORT_PERIOD, 'label': 'Loại', 'align': 'start', 'office_only': True},
        {'key': 'title', 'label': 'Tiêu đề', 'align': 'start', 'office_only': True, 'sortable': False},
        {'key': TEAM_SORT_STATUS, 'label': 'Trạng thái', 'align': 'start'},
        {'key': 'comment', 'label': 'Nhận xét', 'align': 'center', 'sortable': False},
        {'key': TEAM_SORT_REVIEWED, 'label': 'Đã xem', 'align': 'center'},
        {'key': TEAM_SORT_EFFICIENCY, 'label': 'Hiệu suất', 'align': 'center', 'production_only': True},
        {'key': TEAM_SORT_SUMMARY, 'label': 'Tóm tắt', 'align': 'end'},
        {'key': None, 'label': '', 'align': 'end', 'sortable': False},
    ]
    columns = []
    for spec in specs:
        if spec.get('date_column') and not (is_vp or is_production):
            continue
        if spec.get('production_only') and not is_production:
            continue
        if spec.get('office_only') and not is_vp:
            continue
        col = dict(spec)
        if spec.get('date_column') and is_production and not is_vp:
            col['label'] = 'Ngày'
        sortable = spec.get('sortable', spec['key'] is not None)
        col['sortable'] = sortable
        align = col['align']
        col['th_class'] = f'jp-hrm-list-th--{align}'
        if align == 'end':
            col['th_class'] += ' text-end'
        elif align == 'center':
            col['th_class'] += ' text-center'
        if sortable:
            col['sort_href'] = team_sort_href(base_params, spec['key'], sort_key, sort_dir)
            col['sort_active'] = sort_key == spec['key']
            col['sort_dir'] = sort_dir if col['sort_active'] else ''
        columns.append(col)
    return columns


def _member_name(row) -> str:
    member = row['member']
    profile = getattr(member, 'profile', None)
    return (getattr(profile, 'full_name', None) or member.username or '').casefold()


def _date_to_sort_datetime(value: date) -> datetime:
    dt = datetime.combine(value, time.min)
    if timezone.is_aware(dt):
        return dt
    return timezone.make_aware(dt, timezone.get_current_timezone())


def _row_anchor_sort_key(row) -> datetime:
    production_reports = row.get('production_reports') or []
    submitted_times = [
        report.submitted_at
        for report in production_reports
        if getattr(report, 'submitted_at', None)
    ]
    report = row.get('report')
    if not submitted_times and report and report.submitted_at:
        submitted_times = [report.submitted_at]
    if submitted_times:
        return max(submitted_times)

    anchor_date = row.get('report_date')
    if anchor_date is None and report:
        anchor_date = report.report_date
    if anchor_date:
        return _date_to_sort_datetime(anchor_date)
    return _date_to_sort_datetime(date.min)


def _row_sort_tuple(row, sort_key: str) -> tuple:
    report = row.get('report')
    if sort_key == TEAM_SORT_MEMBER:
        return (_member_name(row), row.get('report_date') or date.min)
    if sort_key == TEAM_SORT_ANCHOR:
        return (_row_anchor_sort_key(row),)
    if sort_key == TEAM_SORT_PERIOD:
        if not report:
            return (-1,)
        if report.is_production_report:
            return (0,)
        return (PERIOD_ORDER.get(report.report_period, 99),)
    if sort_key == TEAM_SORT_SHIFT:
        reports = row.get('production_reports') or []
        if reports:
            indices = []
            for report in reports:
                try:
                    indices.append(PRODUCTION_SHIFT_ORDER.index(report.shift))
                except ValueError:
                    indices.append(99)
            return (min(indices),)
        if not report:
            return (-1,)
        try:
            return (PRODUCTION_SHIFT_ORDER.index(report.shift),)
        except ValueError:
            return (99,)
    if sort_key == TEAM_SORT_STATUS:
        if row.get('production_report_count') is not None:
            if not row.get('production_report_count'):
                return (STATUS_ORDER.get(None, 0),)
            if row.get('production_all_submitted'):
                return (STATUS_ORDER.get('SUBMITTED', 0),)
            return (STATUS_ORDER.get('DRAFT', 0),)
        status = report.status if report else None
        return (STATUS_ORDER.get(status, 0),)
    if sort_key == TEAM_SORT_REVIEWED:
        if row.get('production_report_count'):
            return (1 if row.get('production_all_reviewed') else 0,)
        return (1 if report and report.hod_reviewed else 0,)
    if sort_key == TEAM_SORT_EFFICIENCY:
        eff = row.get('production_efficiency_pct')
        return (eff if eff is not None else -1.0,)
    if sort_key == TEAM_SORT_SUMMARY:
        qty = row.get('production_total_qty')
        if qty is not None:
            return (qty, row.get('production_report_count', 0))
        if not report:
            return (0,)
        if report.is_production_report:
            qty = int(getattr(report, 'total_qty', None) or 0)
            lines = int(getattr(report, 'line_count', None) or 0)
            return (qty, lines)
        from reports.office_content import office_report_summary_parts

        return (len(office_report_summary_parts(report)),)
    return (_member_name(row),)


def sort_team_department_groups(department_groups, sort_key: str, sort_dir: str):
    reverse = sort_dir == 'desc'
    return [
        {
            **group,
            'rows': sorted(
                group['rows'],
                key=lambda row: _row_sort_tuple(row, sort_key),
                reverse=reverse,
            ),
        }
        for group in department_groups
    ]
