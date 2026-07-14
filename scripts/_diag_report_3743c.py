"""Inspect 3743 deeply + find similar junk/wrong production drafts."""
from datetime import date, timedelta
from django.utils import timezone
from reports.models import DailyWorkReport, ProductionShiftProduct
from reports.report_profile import REPORT_PROFILE_PRODUCTION

def local_dt(dt):
    if dt is None:
        return None
    return timezone.localtime(dt) if timezone.is_aware(dt) else dt

r = DailyWorkReport.objects.select_related('employee', 'employee__profile').get(pk=3743)
print('=== 3743 full fields ===')
for f in r._meta.fields:
    val = getattr(r, f.name)
    if val not in (None, '', []):
        print(f'  {f.name}: {val}')

print('\n=== products full ===')
for p in ProductionShiftProduct.objects.filter(report=r).prefetch_related('hourly_entries'):
    print('--- product', p.pk)
    for f in p._meta.fields:
        val = getattr(p, f.name)
        if val not in (None, '', []):
            print(f'  {f.name}: {val}')
    for e in p.hourly_entries.all():
        print(f'  entry slot={e.slot_index} qty={e.quantity} dmg={e.damaged_quantity}')

# Drafts Jul 5-14 with very short first product (<60s) or empty product code
print('\n=== Suspicious drafts/submitted Jul 5-14 ===')
qs = (
    DailyWorkReport.objects.filter(
        report_date__gte=date(2026, 7, 5),
        report_date__lte=date(2026, 7, 14),
        report_profile=REPORT_PROFILE_PRODUCTION,
    )
    .select_related('employee', 'employee__profile')
    .prefetch_related('production_products')
    .order_by('report_date', 'id')
)

for rep in qs:
    products = list(rep.production_products.all())
    name = getattr(getattr(rep.employee, 'profile', None), 'full_name', None) or rep.employee.username
    flags = []
    if not products:
        flags.append('EMPTY')
    for p in products:
        code = (getattr(p, 'product_code', None) or getattr(p, 'code', None) or '').strip()
        pname = (getattr(p, 'product_name', None) or '').strip()
        if not code and not pname:
            flags.append(f'NO_CODE#{p.id}')
        st, en = local_dt(p.started_at), local_dt(p.ended_at)
        if st and en:
            dur = (en - st).total_seconds()
            if dur < 60:
                flags.append(f'INSTANT#{p.id}({dur:.0f}s)')
    # overnight morning start
    st = local_dt(rep.shift_started_at)
    if st and st.hour < 6:
        flags.append(f'EARLY_START({st.strftime("%H:%M")})')
    if flags:
        print(
            f'  #{rep.id} {rep.report_date} {rep.shift} {rep.status} {name} '
            f'products={len(products)} flags={flags}'
        )

# Count all production reports in range by status
print('\n=== Counts Jul 5-14 ===')
from django.db.models import Count
print(list(
    DailyWorkReport.objects.filter(
        report_date__gte=date(2026, 7, 5),
        report_date__lte=date(2026, 7, 14),
        report_profile=REPORT_PROFILE_PRODUCTION,
    ).values('status', 'shift').annotate(c=Count('id')).order_by('status', 'shift')
))
