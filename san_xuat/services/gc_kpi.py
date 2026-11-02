"""KPI đối tác gia công theo tháng.

- SL báo / SL duyệt / tỉ lệ đạt QC = duyệt ÷ báo (báo cáo đã xử lý trong tháng theo ngày SX).
- Đúng hạn = phiếu hoàn thành trong tháng có ngày nhận ≤ hạn.
- Thành tiền = Σ SL duyệt × đơn giá phiếu.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal

from san_xuat.hub_models import SxSubcontractOrder
from san_xuat.partner_models import GcOutputReport

ZERO = Decimal('0')


def _month_range(month: str) -> tuple[date, date, str]:
    try:
        y, m = (int(x) for x in (month or '').split('-')[:2])
        start = date(y, m, 1)
    except (TypeError, ValueError):
        today = date.today()
        start = today.replace(day=1)
    end = start.replace(day=monthrange(start.year, start.month)[1])
    return start, end, f'{start.year:04d}-{start.month:02d}'


def partner_kpi(partner, *, month: str = '') -> dict:
    start, end, month_value = _month_range(month)
    reports = list(
        GcOutputReport.objects.filter(partner=partner, work_date__range=(start, end))
        .select_related('order')
    )
    reported = approved = pending_qty = amount = ZERO
    rejected_n = 0
    by_day: dict[date, Decimal] = {}
    for r in reports:
        if r.status == GcOutputReport.STATUS_SUBMITTED:
            pending_qty += r.total_qty
            continue
        reported += r.total_qty
        if r.status == GcOutputReport.STATUS_REJECTED:
            rejected_n += 1
            continue
        approved += r.approved_qty
        amount += (r.approved_qty * (r.order.unit_price or ZERO))
        by_day[r.work_date] = by_day.get(r.work_date, ZERO) + r.approved_qty
    pass_rate = (approved * 100 / reported).quantize(Decimal('0.1')) if reported else None

    done_orders = list(
        SxSubcontractOrder.objects.filter(
            partner=partner,
            status__in=[SxSubcontractOrder.STATUS_RECEIVED, SxSubcontractOrder.STATUS_DONE],
            received_at__date__range=(start, end),
        )
    )
    with_due = [o for o in done_orders if o.due_date]
    on_time = [o for o in with_due if o.received_at.date() <= o.due_date]
    on_time_rate = (
        (Decimal(len(on_time)) * 100 / len(with_due)).quantize(Decimal('0.1')) if with_due else None
    )
    days = sorted(by_day.items())
    return {
        'month_value': month_value,
        'start': start,
        'end': end,
        'reported': reported,
        'approved': approved,
        'pending_qty': pending_qty,
        'rejected_n': rejected_n,
        'pass_rate': pass_rate,
        'amount': amount.quantize(Decimal('1')),
        'done_orders': len(done_orders),
        'with_due': len(with_due),
        'on_time': len(on_time),
        'on_time_rate': on_time_rate,
        'by_day': days,
        'max_day': max((q for _d, q in days), default=ZERO),
    }
