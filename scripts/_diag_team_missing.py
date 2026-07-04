from datetime import date

from django.contrib.auth.models import User

from hrm.permissions import get_team_report_members
from reports.models import DailyWorkReport
from reports.production_team import (
    build_production_reports_by_employee,
    build_production_team_department_groups,
    production_team_row_is_submitted,
    query_production_team_reports,
)
from reports.report_profile import REPORT_PROFILE_PRODUCTION
from reports.team_utils import daily_report_visible_to_team
from reports.views import _filter_team_department_groups, TEAM_STATUS_MISSING

leader = User.objects.filter(username__iexact='Vuonglnt').first()
today = date(2026, 7, 4)
team = get_team_report_members(leader).filter(
    profile__department__report_profile=REPORT_PROFILE_PRODUCTION,
)
ids = list(team.values_list('id', flat=True))
reports = query_production_team_reports(ids, today, today)
by_emp = build_production_reports_by_employee(reports)
groups, _ = build_production_team_department_groups(
    leader,
    team,
    by_emp,
    daily_report_visible_to_team,
    date_from=today,
    date_to=today,
)
filtered = _filter_team_department_groups(
    groups,
    TEAM_STATUS_MISSING,
    submitted_status=DailyWorkReport.STATUS_SUBMITTED,
    row_is_submitted=lambda row, **kw: production_team_row_is_submitted(row, submitted_status=DailyWorkReport.STATUS_SUBMITTED),
)
print('all rows:', sum(len(g['rows']) for g in groups))
print('missing rows:', sum(len(g['rows']) for g in filtered))
for g in filtered:
    for row in g['rows']:
        u = row['member'].username
        rd = row.get('report_date')
        cnt = row.get('production_report_count')
        submitted = production_team_row_is_submitted(row, submitted_status=DailyWorkReport.STATUS_SUBMITTED)
        statuses = [r.status for r in (row.get('production_reports') or [])]
        print(u, rd, 'count', cnt, 'statuses', statuses, 'is_submitted', submitted)

test_rows_all = [row for g in groups for row in g['rows'] if row['member'].username == 'test']
test_rows_missing = [row for g in filtered for row in g['rows'] if row['member'].username == 'test']
print('test in all:', len(test_rows_all), 'test in missing:', len(test_rows_missing))
