"""Check whether SL=0 hours are included in thời gian thực tế."""
from reports.models import DailyWorkReport
from reports.production_hourly import (
    build_productivity_report,
    compute_day_work_waste_summary,
    list_production_products,
    _product_accounted_work_hours,
    _product_is_zero_reason_only,
    session_effective_hours,
)

for pk in (4789, 4765, 4752, 4684, 4681):
    r = DailyWorkReport.objects.prefetch_related(
        'production_products__hourly_entries'
    ).get(pk=pk)
    products = list_production_products(r)
    zero_session = 0.0
    pos_accounted = 0.0
    zero_accounted = 0.0
    print(f'#{pk} declared={r.declared_work_hours}')
    for p in products:
        h = float(_product_accounted_work_hours(p))
        sess = (
            float(session_effective_hours(p))
            if p.started_at and p.ended_at
            else 0.0
        )
        zo = _product_is_zero_reason_only(p)
        if zo or (p.total_quantity is not None and float(p.total_quantity) == 0):
            zero_session += sess
            zero_accounted += h
            print(
                f'  ZERO id={p.id} accounted={h} session={sess} '
                f'zero_only={zo} note={(p.completion_note or "")[:40]!r}'
            )
        else:
            pos_accounted += h
    day = compute_day_work_waste_summary(r, products)
    prod = build_productivity_report(r)
    ds = prod['day_summary']
    print(
        f'  pos_accounted={pos_accounted:.2f} zero_accounted={zero_accounted:.2f} '
        f'zero_session={zero_session:.2f} work={day["work_minutes_display"]} '
        f'time_eff={day["time_efficiency_pct"]} qty_eff={ds["quantity_efficiency_pct"]} '
        f'avg={ds["avg_efficiency_pct"]}'
    )
    print('---')
