"""Diag report 3743 and similar wrong night/OT reports."""
from datetime import date, timedelta
from collections import defaultdict

from django.utils import timezone

from reports.models import DailyWorkReport
from reports.report_profile import REPORT_PROFILE_PRODUCTION
from reports.management.commands.fix_misclassified_night_ot import (
    is_misclassified_morning_overtime,
)

r = DailyWorkReport.objects.select_related('employee', 'employee__profile').prefetch_related(
    'production_products__hourly_entries'
).get(pk=3743)
name = getattr(getattr(r.employee, 'profile', None), 'full_name', None) or r.employee.username
print('=== REPORT 3743 ===')
print('employee', r.employee_id, name, r.employee.username)
print('date', r.report_date, 'shift', r.shift, 'status', r.status, 'profile', r.report_profile)
print('shift_started_at', r.shift_started_at)
print('products', r.production_products.count())
for p in r.production_products.all():
    print(
        '  product', p.id,
        getattr(p, 'product_code', None),
        getattr(p, 'operation_name', None) or getattr(p, 'step_name', None),
        'started', p.started_at, 'ended', p.ended_at,
    )
    for e in p.hourly_entries.all():
        qty = e.quantity or 0
        dmg = e.damaged_quantity or 0
        if qty or dmg:
            print('    slot', e.slot_index, 'qty', qty, 'dmg', dmg)

others = list(
    DailyWorkReport.objects.filter(
        employee_id=r.employee_id,
        report_date=r.report_date,
        report_profile=REPORT_PROFILE_PRODUCTION,
    ).exclude(pk=r.pk)
)
print('other same day:', [(o.id, o.shift, o.status) for o in others])

# Same employee recent reports Jul 5-14
print('\n=== Same employee reports 2026-07-05..14 ===')
for o in DailyWorkReport.objects.filter(
    employee_id=r.employee_id,
    report_date__gte=date(2026, 7, 5),
    report_date__lte=date(2026, 7, 14),
    report_profile=REPORT_PROFILE_PRODUCTION,
).order_by('report_date', 'shift'):
    n = o.production_products.count()
    print(f'  #{o.id} {o.report_date} {o.shift} status={o.status} products={n} started={o.shift_started_at}')

# Find night reports that look wrong: NIGHT with morning coworker same day,
# OR NIGHT with no overnight work, OR OVERTIME shift (legacy?)
print('\n=== Scan period 2026-07-05..14 for suspicious ===')
qs = (
    DailyWorkReport.objects.filter(
        report_date__gte=date(2026, 7, 5),
        report_date__lte=date(2026, 7, 14),
        report_profile=REPORT_PROFILE_PRODUCTION,
    )
    .select_related('employee', 'employee__profile')
    .prefetch_related('production_products__hourly_entries')
    .order_by('report_date', 'employee_id', 'shift')
)

by_key = defaultdict(list)
for rep in qs:
    by_key[(rep.employee_id, rep.report_date)].append(rep)

print('--- OVERTIME shift reports ---')
for rep in qs:
    if rep.shift == 'OVERTIME':
        name = getattr(getattr(rep.employee, 'profile', None), 'full_name', None) or rep.employee.username
        print(f'  #{rep.id} {rep.report_date} {name} products={rep.production_products.count()}')

print('--- NIGHT alone (no morning same day) ---')
for (emp, day), reps in sorted(by_key.items(), key=lambda x: (x[0][1], x[0][0])):
    shifts = {x.shift: x for x in reps}
    night = shifts.get('NIGHT')
    morning = shifts.get('MORNING')
    if not night:
        continue
    name = getattr(getattr(night.employee, 'profile', None), 'full_name', None) or night.employee.username
    n_prod = night.production_products.count()
    if morning:
        mis = is_misclassified_morning_overtime(night, morning)
        print(f'  BOTH #{night.id}+#{morning.id} {day} {name} night_products={n_prod} misclassified={mis}')
    else:
        # night only — check if looks like morning OT (no overnight)
        # create fake empty morning? Just flag nights with only early slots / empty / before midnight
        products = list(night.production_products.all())
        overnight = False
        for p in products:
            for e in p.hourly_entries.all():
                if e.slot_index >= 6 and ((e.quantity or 0) or (e.damaged_quantity or 0)):
                    overnight = True
            for ts in (p.started_at, p.ended_at):
                if not ts:
                    continue
                local = timezone.localtime(ts) if timezone.is_aware(ts) else ts
                if local.date() > day:
                    overnight = True
        flag = 'SUSPECT_NO_OVERNIGHT' if (not overnight) else 'OK_OVERNIGHT'
        print(f'  NIGHT_ONLY #{night.id} {day} {name} products={n_prod} {flag} status={night.status}')
