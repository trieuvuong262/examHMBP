"""Find morning reports that started in night window (0h-5h) — wrong dating/shift."""
from datetime import date, time, datetime, timedelta
from collections import defaultdict

from django.utils import timezone

from reports.models import DailyWorkReport
from reports.report_profile import REPORT_PROFILE_PRODUCTION

LOCAL_TZ = timezone.get_current_timezone()

def local_dt(dt):
    if dt is None:
        return None
    if timezone.is_aware(dt):
        return timezone.localtime(dt)
    return timezone.make_aware(dt, LOCAL_TZ)

print('timezone', LOCAL_TZ)
r = DailyWorkReport.objects.select_related('employee', 'employee__profile').prefetch_related(
    'production_products__hourly_entries'
).get(pk=3743)
print('3743 UTC started', r.shift_started_at)
print('3743 local started', local_dt(r.shift_started_at))
for p in r.production_products.all():
    print('  prod', p.id, 'start local', local_dt(p.started_at), 'end local', local_dt(p.ended_at))
    for e in p.hourly_entries.all():
        qty = e.quantity or 0
        dmg = e.damaged_quantity or 0
        if qty or dmg:
            print('    slot', e.slot_index, 'qty', qty)

# Suspect: MORNING reports whose shift_started_at local time is before 06:30
# OR NIGHT reports dated as next calendar day incorrectly
# OR MORNING started 00:00-05:59

print('\n=== MORNING started before 06:30 local (2026-07-01..14) ===')
qs = (
    DailyWorkReport.objects.filter(
        report_date__gte=date(2026, 7, 1),
        report_date__lte=date(2026, 7, 14),
        report_profile=REPORT_PROFILE_PRODUCTION,
        shift='MORNING',
        shift_started_at__isnull=False,
    )
    .select_related('employee', 'employee__profile')
    .prefetch_related('production_products')
    .order_by('report_date', 'id')
)

suspects = []
for rep in qs:
    st = local_dt(rep.shift_started_at)
    if st is None:
        continue
    if st.time() < time(6, 30):
        name = getattr(getattr(rep.employee, 'profile', None), 'full_name', None) or rep.employee.username
        nprod = rep.production_products.count()
        suspects.append(rep)
        print(
            f'  #{rep.id} {rep.report_date} {name} (@{rep.employee.username}) '
            f'started_local={st.isoformat()} status={rep.status} products={nprod}'
        )

print(f'Total suspects: {len(suspects)}')

# Also: any MORNING with product activity only in early hours that looks like night continuation
print('\n=== Also check: report_date vs started local date mismatch ===')
for rep in DailyWorkReport.objects.filter(
    report_date__gte=date(2026, 7, 1),
    report_date__lte=date(2026, 7, 14),
    report_profile=REPORT_PROFILE_PRODUCTION,
    shift_started_at__isnull=False,
).select_related('employee', 'employee__profile'):
    st = local_dt(rep.shift_started_at)
    if st and st.date() != rep.report_date:
        name = getattr(getattr(rep.employee, 'profile', None), 'full_name', None) or rep.employee.username
        print(f'  #{rep.id} report_date={rep.report_date} shift={rep.shift} started_local={st.date()} {st.time()} {name}')
