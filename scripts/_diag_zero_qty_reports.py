"""Tìm BC SX có công đoạn SL=0 và kiểm tra hiển thị trên chi tiết (productivity)."""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Q
from django.urls import reverse

from reports.models import DailyWorkReport, ProductionHourlyQuantity, ProductionShiftProduct
from reports.production_hourly import (
    _product_is_zero_reason_only,
    _products_for_productivity,
    build_hourly_grid,
    build_productivity_report,
    list_production_products,
)


def _is_zero_qty_product(product: ProductionShiftProduct) -> bool:
    if _product_is_zero_reason_only(product):
        return True
    if product.total_quantity is not None and Decimal(str(product.total_quantity)) == 0:
        return True
    has_filled_zero = False
    has_positive = False
    for entry in product.hourly_entries.all():
        qty = entry.quantity or Decimal('0')
        reason = (entry.zero_reason or '').strip()
        if qty > 0:
            has_positive = True
        elif reason or qty == 0:
            if qty == 0 and (reason or product.total_quantity == 0):
                has_filled_zero = True
    return has_filled_zero and not has_positive


zero_entry_product_ids = set(
    ProductionHourlyQuantity.objects.filter(
        Q(quantity=0) & (~Q(zero_reason='') | Q(product__total_quantity=0))
    ).values_list('product_id', flat=True)
)
zero_total_product_ids = set(
    ProductionShiftProduct.objects.filter(total_quantity=0).values_list('id', flat=True)
)
candidate_ids = zero_entry_product_ids | zero_total_product_ids

products = list(
    ProductionShiftProduct.objects.filter(id__in=candidate_ids)
    .select_related('report', 'report__employee', 'report__employee__profile')
    .prefetch_related('hourly_entries')
    .order_by('-report__report_date', '-report_id', 'sort_order', 'id')
)

rows = []
for product in products:
    if not _is_zero_qty_product(product):
        continue
    report = product.report
    if not report or not report.is_production_report:
        continue
    rows.append((report, product))

# unique reports, keep first few products
by_report: dict[int, list] = {}
for report, product in rows:
    by_report.setdefault(report.pk, []).append(product)

print(f'FOUND_REPORTS={len(by_report)} ZERO_PRODUCTS={len(rows)}')
print('---')

checked = 0
ok = 0
fail = 0
samples = []

for report_id, prods in list(by_report.items())[:25]:
    report = prods[0].report
    all_products = list_production_products(report)
    productivity = build_productivity_report(report)
    grid = build_hourly_grid(report)
    summary_ids = set(productivity.get('summary_product_ids') or [])
    productive_ids = {p.id for p in _products_for_productivity(all_products)}
    grid_ids = {row['id'] for row in grid.get('rows') or []}

    zero_ids = [p.id for p in prods]
    missing_summary = [pid for pid in zero_ids if pid not in summary_ids]
    wrongly_in_eff = [pid for pid in zero_ids if pid in productive_ids]
    missing_grid = [pid for pid in zero_ids if pid not in grid_ids]

    profile = getattr(report.employee, 'profile', None)
    name = (profile.full_name if profile and profile.full_name else report.employee.username)
    detail_path = reverse('reports:detail_cn', args=[report.pk])

    status = 'OK'
    if missing_summary or wrongly_in_eff:
        status = 'FAIL'
        fail += 1
    else:
        ok += 1
    checked += 1

    reason = ''
    for p in prods[:2]:
        from reports.production_hourly import _product_zero_reason
        reason = _product_zero_reason(p) or reason

    zero_summaries = [
        s for s in productivity.get('product_summaries') or []
        if s.get('product_id') in zero_ids
    ]
    eff_values = [s.get('efficiency_pct') for s in zero_summaries]

    line = (
        f'{status} report={report.pk} date={report.report_date} shift={report.shift} '
        f'status={report.status} emp={name!r} zero_steps={len(zero_ids)} '
        f'missing_summary={missing_summary} in_eff={wrongly_in_eff} '
        f'missing_grid={missing_grid} zero_eff={eff_values} '
        f'reason={reason[:60]!r} url={detail_path}'
    )
    print(line)
    if status == 'OK' and len(samples) < 8:
        samples.append({
            'pk': report.pk,
            'date': str(report.report_date),
            'shift': report.shift,
            'emp': name,
            'url': detail_path,
            'zero_count': len(zero_ids),
            'reason': reason[:80],
            'qty_eff': productivity.get('day_summary', {}).get('quantity_efficiency_pct'),
            'summaries': [
                {
                    'code': s.get('product_code'),
                    'process': s.get('process_name'),
                    'qty': s.get('quantity'),
                    'eff': s.get('efficiency_pct'),
                    'hours': s.get('hours_display'),
                    'zero': s.get('is_zero_reason_only'),
                }
                for s in zero_summaries
            ],
        })

print('---')
print(f'CHECKED={checked} OK={ok} FAIL={fail}')
print('SAMPLES:')
for s in samples:
    print(
        f"  #{s['pk']} {s['date']} {s['shift']} {s['emp']} "
        f"zero={s['zero_count']} qty_eff={s['qty_eff']} url={s['url']}"
    )
    for row in s['summaries']:
        print(
            f"    - {row['code']} | {row['process']} | SL={row['qty']} "
            f"| HS={row['eff']} | {row['hours']} | zero_flag={row['zero']}"
        )
