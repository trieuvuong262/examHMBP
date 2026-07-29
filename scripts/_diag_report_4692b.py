from reports.models import DailyWorkReport, DailyWorkReportEditLog
from reports.production_report_reminders import auto_submit_one_report, can_auto_submit_report, KIND_MORNING
from reports.production_hourly import (
    validate_production_submit_efficiency,
    product_has_efficiency_anomaly,
    _product_efficiency_pct,
    product_has_zero_duration_anomaly,
)
from django.utils import timezone

r = DailyWorkReport.objects.get(pk=4692)
print('status', r.status)
print('can', can_auto_submit_report(r, kind=KIND_MORNING))
print('dry', auto_submit_one_report(r, kind=KIND_MORNING, dry_run=True))
for p in r.production_products.all():
    print(
        p.pk, p.product_code,
        'norm', p.norm_per_hour,
        'qty', p.total_quantity,
        'zero', product_has_zero_duration_anomaly(p),
        'anom', product_has_efficiency_anomaly(p),
        'eff', _product_efficiency_pct(p),
        'start', p.started_at,
        'end', p.ended_at,
    )
print('overall', validate_production_submit_efficiency(r))
print('manager fix log:')
for e in DailyWorkReportEditLog.objects.filter(report_id=4692).order_by('-edited_at')[:3]:
    print(timezone.localtime(e.edited_at), e.action, e.summary)
    print(' detail:', (e.detail or '')[:800])
