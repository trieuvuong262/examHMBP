"""Diagnose why report 4692 was not auto-submitted."""
from datetime import date, datetime, timedelta
from django.db.models import Count
from django.utils import timezone

from reports.models import (
    DailyWorkReport,
    DailyWorkReportEditLog,
    ProductionReportReminderLog,
    ReportsGeneralSettings,
)
from reports.production_hourly import (
    build_hourly_grid,
    unfinalized_active_with_data,
    validate_production_submit_efficiency,
)
from reports.production_report_reminders import (
    KIND_MORNING,
    KIND_NIGHT,
    _configured_auto_submit_time,
    auto_submit_report_date,
    can_auto_submit_report,
    is_auto_submit_window,
)
from reports.report_profile import REPORT_PROFILE_PRODUCTION

PK = 4692
r = DailyWorkReport.objects.select_related('employee', 'employee__profile').get(pk=PK)
print('pk', r.pk, 'emp', r.employee.username, r.employee.profile.full_name)
print('date', r.report_date, 'shift', r.shift, 'status', r.status, 'auto', r.auto_submitted)
print('hours', r.declared_work_hours, 'started', r.shift_started_at)

grid = build_hourly_grid(r)
print('grand_total', grid.get('grand_total'), 'rows', len(grid.get('rows') or []))
print('blocker', unfinalized_active_with_data(r))
_, eff = validate_production_submit_efficiency(r)
print('efficiency', repr(eff))
print('can_morning', can_auto_submit_report(r, kind=KIND_MORNING))

d = date(2026, 7, 28)
qs = DailyWorkReport.objects.filter(
    report_profile=REPORT_PROFILE_PRODUCTION,
    report_date=d,
).exclude(shift='NIGHT')
print('morning_28 status', dict(qs.values('status').annotate(c=Count('id')).values_list('status', 'c')))
print('auto_submitted', qs.filter(auto_submitted=True).count())
print('draft_count', qs.filter(status='DRAFT').count())
for row in qs.filter(status='DRAFT').select_related('employee', 'employee__profile').order_by('id'):
    ok, reason = can_auto_submit_report(row, kind=KIND_MORNING)
    name = row.employee.profile.full_name or row.employee.username
    print(f'  DRAFT {row.pk} {name} can={ok} reason={reason!r} hours={row.declared_work_hours}')

print('reminder_logs_28', ProductionReportReminderLog.objects.filter(report_date=d).count())
print('sample auto submit times:')
for row in qs.filter(auto_submitted=True).order_by('submitted_at')[:3]:
    print(' ', row.pk, timezone.localtime(row.submitted_at), row.employee.username)
for row in qs.filter(auto_submitted=True).order_by('-submitted_at')[:3]:
    print(' ', row.pk, timezone.localtime(row.submitted_at), row.employee.username)

print('edit_logs 4692:')
for e in DailyWorkReportEditLog.objects.filter(report_id=PK).order_by('-edited_at')[:10]:
    print(' ', timezone.localtime(e.edited_at), e.action, (e.summary or '')[:120])

# Was 4692 even created before 23:30?
print('updated_at', timezone.localtime(r.updated_at), 'created?', getattr(r, 'created_at', None))

# Simulate window on 28 at 23:32
fake = timezone.make_aware(datetime(2026, 7, 28, 23, 32))
print('fake window 28 23:32 morning', is_auto_submit_window(now=fake, kind=KIND_MORNING))
print('fake target date', auto_submit_report_date(now=fake, kind=KIND_MORNING))
print('cfg', ReportsGeneralSettings.load().auto_submit_time, _configured_auto_submit_time(KIND_MORNING))
