from datetime import date

from django.contrib.auth import get_user_model

from hrm.models import Employee
from reports.models import DailyWorkReport
from reports.production_team import (
    build_production_reports_by_employee,
    build_production_team_department_groups,
    production_team_row_matches_filter,
    production_team_status_counts,
    query_production_team_reports,
)
from reports.visibility import daily_report_visible_to_team

leader = Employee.objects.filter(user__username='Vuonglnt').first()
if not leader:
    print('no leader')
    raise SystemExit(1)

team = leader.direct_subordinates.filter(report_profile='production')
team_ids = list(team.values_list('id', flat=True))
d = date(2026, 7, 4)
reports = query_production_team_reports(team_ids, d, d)
by_emp = build_production_reports_by_employee(reports)
counts = production_team_status_counts(team_ids, by_emp, daily_report_visible_to_team)
print('team_size', len(team_ids), 'counts', counts)

User = get_user_model()
u = User.objects.get(username='Vuonglnt')
groups, _ = build_production_team_department_groups(
    u, team, by_emp, daily_report_visible_to_team, date_from=d, date_to=d,
)
for group in groups:
    for row in group['rows']:
        username = row['employee'].user.username
        if username == 'test':
            missing = production_team_row_matches_filter(
                row, 'missing', submitted_status=DailyWorkReport.STATUS_SUBMITTED,
            )
            no_report = production_team_row_matches_filter(
                row, 'no_report', submitted_status=DailyWorkReport.STATUS_SUBMITTED,
            )
            print(
                'test',
                'reports', row.get('production_report_count'),
                'missing_filter', missing,
                'no_report_filter', no_report,
            )
