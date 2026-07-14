"""List then delete DRAFT production reports flagged as «Báo cáo sai» (anomaly)."""
from datetime import date

from reports.models import DailyWorkReport
from reports.production_hourly import (
    anomaly_product_ids_for_report,
    report_has_manager_fixable_anomaly,
    product_has_zero_duration_anomaly,
    product_has_efficiency_anomaly,
    _product_efficiency_pct,
)
from reports.report_profile import REPORT_PROFILE_PRODUCTION

FROM = date(2026, 7, 5)
TO = date(2026, 7, 14)
APPLY = False  # set True by wrapper

qs = (
    DailyWorkReport.objects.filter(
        report_date__gte=FROM,
        report_date__lte=TO,
        report_profile=REPORT_PROFILE_PRODUCTION,
        status=DailyWorkReport.STATUS_DRAFT,
    )
    .select_related('employee', 'employee__profile')
    .prefetch_related('production_products__hourly_entries')
    .order_by('report_date', 'id')
)

bad = []
for r in qs:
    if not report_has_manager_fixable_anomaly(r):
        continue
    name = getattr(getattr(r.employee, 'profile', None), 'full_name', None) or r.employee.username
    anom_ids = anomaly_product_ids_for_report(r)
    reasons = []
    for p in r.production_products.all():
        if p.id not in anom_ids:
            continue
        if product_has_zero_duration_anomaly(p):
            reasons.append(f'#{p.id} zero_dur')
        elif product_has_efficiency_anomaly(p):
            eff = _product_efficiency_pct(p)
            reasons.append(f'#{p.id} eff={eff}')
    bad.append(r)
    print(
        f'  #{r.id} {r.report_date} {r.shift} {name} '
        f'products={r.production_products.count()} anom={sorted(anom_ids)} {reasons}'
    )

print(f'\nTotal BAD reports: {len(bad)}')
print('ids:', [r.id for r in bad])

# Special check 3743
r3743 = DailyWorkReport.objects.filter(pk=3743).first()
if r3743:
    print('3743 is_bad?', report_has_manager_fixable_anomaly(r3743),
          'anom', anomaly_product_ids_for_report(r3743))

if APPLY and bad:
    ids = [r.id for r in bad]
    deleted, detail = DailyWorkReport.objects.filter(id__in=ids).delete()
    print(f'\nDELETED count={deleted} detail={detail}')
elif not APPLY:
    print('\nDry-run — set APPLY=True to delete.')
