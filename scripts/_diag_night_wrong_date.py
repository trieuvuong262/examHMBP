"""Find night reports with wrong report_date (after-midnight start dated as today instead of prev day)."""
from datetime import date, time, timedelta
from django.utils import timezone
from reports.models import DailyWorkReport
from reports.report_profile import REPORT_PROFILE_PRODUCTION

def local_dt(dt):
    if dt is None:
        return None
    return timezone.localtime(dt) if timezone.is_aware(dt) else dt

print('=== NIGHT reports where start local hour < 5 AND report_date == start.date() (should be prev day) ===')
qs = DailyWorkReport.objects.filter(
    report_date__gte=date(2026, 7, 1),
    report_date__lte=date(2026, 7, 14),
    report_profile=REPORT_PROFILE_PRODUCTION,
    shift='NIGHT',
).select_related('employee', 'employee__profile').prefetch_related('production_products__hourly_entries')

wrong_night_date = []
for r in qs:
    name = getattr(getattr(r.employee, 'profile', None), 'full_name', None) or r.employee.username
    st = local_dt(r.shift_started_at)
    products = list(r.production_products.all())
    print(f'\n#{r.id} date={r.report_date} {name} status={r.status} started={st} products={len(products)}')
    for p in products:
        pst = local_dt(p.started_at)
        pen = local_dt(p.ended_at)
        print(f'  prod#{p.id} code={p.product_code!r} process={p.process_name!r} start={pst} end={pen} status={p.status}')
        for e in p.hourly_entries.all():
            qty = e.quantity or 0
            dmg = e.damaged_quantity or 0
            if qty or dmg:
                print(f'    slot {e.slot_index} qty={qty} dmg={dmg}')
    if st and st.time() < time(5, 0) and st.date() == r.report_date:
        wrong_night_date.append(r.id)
        print('  >>> WRONG_DATE: night after midnight dated as calendar day of start')

print('\nwrong_night_date ids', wrong_night_date)

# Also: MORNING reports that have activity ONLY consistent with night (slots?) 
# Check 3743 sibling / what manager list shows for ngoc
print('\n=== Detail 3743 products qty slots timing vs morning slots ===')
r = DailyWorkReport.objects.get(pk=3743)
print('report', r.report_date, r.shift, r.status)
print('created local', local_dt(r.created_at))
print('started local', local_dt(r.shift_started_at))

# Render what list row might show - check if hod view filters
print('\n=== All reports id around 3743 ===')
for r in DailyWorkReport.objects.filter(id__gte=3740, id__lte=3745).select_related('employee','employee__profile'):
    name = getattr(getattr(r.employee, 'profile', None), 'full_name', None) or r.employee.username
    print(f'#{r.id} {r.report_date} {r.shift} {r.status} {name}')
