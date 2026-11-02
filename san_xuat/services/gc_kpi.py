"""KPI đối tác gia công theo tháng.

Chỉ tiêu (trọng số):
- Chất lượng 40%: SL duyệt ÷ SL báo (báo cáo QC đã xử lý, theo ngày SX trong tháng).
- Đúng hạn 30%: phiếu nhận lại trong tháng có ngày nhận ≤ hạn ÷ phiếu có hạn.
- Đạt kế hoạch 20%: SL duyệt tới hạn (≤ SL phiếu) ÷ SL phiếu, các phiếu có hạn trong tháng.
- Phản hồi đơn 10%: phiếu gửi trong tháng được nhận / từ chối trong vòng 24 giờ.

Điểm = Σ tỷ lệ × trọng số, chia lại trên các chỉ tiêu có dữ liệu. Hạng A ≥ 90, B ≥ 75, còn lại C.
Thành tiền = Σ SL duyệt × đơn giá phiếu (gồm cả phần vượt SL phiếu).
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from san_xuat.hub_models import SxSubcontractOrder
from san_xuat.partner_models import GcKpiSnapshot, GcOutputReport

ZERO = Decimal('0')
RESPONSE_HOURS = 24
KPI_WEIGHTS = (
    ('quality', 'Chất lượng', Decimal('40')),
    ('on_time', 'Đúng hạn', Decimal('30')),
    ('plan', 'Đạt kế hoạch', Decimal('20')),
    ('response', 'Phản hồi đơn', Decimal('10')),
)
GRADE_A = Decimal('90')
GRADE_B = Decimal('75')


def _month_range(month: str) -> tuple[date, date, str]:
    try:
        y, m = (int(x) for x in (month or '').split('-')[:2])
        start = date(y, m, 1)
    except (TypeError, ValueError):
        today = date.today()
        start = today.replace(day=1)
    end = start.replace(day=monthrange(start.year, start.month)[1])
    return start, end, f'{start.year:04d}-{start.month:02d}'


def _rate(num, den) -> Decimal | None:
    return (Decimal(num) * 100 / Decimal(den)).quantize(Decimal('0.1')) if den else None


def grade_for(score: Decimal | None) -> str:
    if score is None:
        return ''
    if score >= GRADE_A:
        return 'A'
    if score >= GRADE_B:
        return 'B'
    return 'C'


def kpi_score(rates: dict[str, Decimal | None]) -> Decimal | None:
    """Điểm 0–100; chỉ tiêu chưa có dữ liệu bỏ qua và chia lại trọng số."""
    total_w = ZERO
    acc = ZERO
    for key, _label, weight in KPI_WEIGHTS:
        rate = rates.get(key)
        if rate is None:
            continue
        acc += min(Decimal(rate), Decimal('100')) * weight
        total_w += weight
    return (acc / total_w).quantize(Decimal('0.1')) if total_w else None


def partner_kpi(partner, *, month: str = '') -> dict:
    start, end, month_value = _month_range(month)
    reports = list(
        GcOutputReport.objects.filter(partner=partner, work_date__range=(start, end))
        .exclude(status=GcOutputReport.STATUS_CANCELLED)
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
    pass_rate = _rate(approved, reported) if reported else None

    done_orders = list(
        SxSubcontractOrder.objects.filter(
            partner=partner,
            is_demo=False,
            status__in=[SxSubcontractOrder.STATUS_RECEIVED, SxSubcontractOrder.STATUS_DONE],
            received_at__date__range=(start, end),
        )
    )
    with_due = [o for o in done_orders if o.due_date]
    on_time = [o for o in with_due if o.received_at.date() <= o.due_date]
    on_time_rate = _rate(len(on_time), len(with_due))

    # Đạt kế hoạch: phiếu có hạn trong tháng — SL duyệt (theo ngày SX ≤ hạn) so với SL phiếu.
    plan_orders = list(
        SxSubcontractOrder.objects.filter(
            partner=partner, is_demo=False, due_date__range=(start, end),
        ).exclude(status=SxSubcontractOrder.STATUS_CANCELLED)
        .filter(Q(partner_sent_at__isnull=False) | Q(output_reports__isnull=False))
        .distinct()
    )
    plan_qty = plan_done = ZERO
    for o in plan_orders:
        got = sum(
            (r.approved_qty for r in o.output_reports.filter(
                status=GcOutputReport.STATUS_APPROVED, work_date__lte=o.due_date,
            )),
            ZERO,
        )
        plan_qty += o.qty or ZERO
        plan_done += min(got, o.qty or ZERO)
    plan_rate = _rate(plan_done, plan_qty)

    # Phản hồi đơn: phiếu gửi trong tháng, nhận/từ chối trong RESPONSE_HOURS giờ.
    sent_orders = list(
        SxSubcontractOrder.objects.filter(
            partner=partner, is_demo=False, partner_sent_at__date__range=(start, end),
        )
    )
    limit = timedelta(hours=RESPONSE_HOURS)
    responded = 0
    for o in sent_orders:
        at = o.partner_accepted_at or o.partner_rejected_at
        if at and at - o.partner_sent_at <= limit:
            responded += 1
    response_rate = _rate(responded, len(sent_orders))

    rates = {'quality': pass_rate, 'on_time': on_time_rate, 'plan': plan_rate, 'response': response_rate}
    score = kpi_score(rates)
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
        'plan_qty': plan_qty,
        'plan_done': plan_done,
        'plan_rate': plan_rate,
        'sent_orders': len(sent_orders),
        'responded': responded,
        'response_rate': response_rate,
        'response_hours': RESPONSE_HOURS,
        'score': score,
        'grade': grade_for(score),
        'criteria': [
            {'key': key, 'label': label, 'weight': weight, 'rate': rates[key]}
            for key, label, weight in KPI_WEIGHTS
        ],
        'by_day': days,
        'max_day': max((q for _d, q in days), default=ZERO),
    }


# ---------------------------------------------------------------------------
# Chốt KPI tháng
# ---------------------------------------------------------------------------

def _jsonable(kpi: dict) -> dict:
    keep = (
        'reported', 'approved', 'pending_qty', 'rejected_n', 'pass_rate', 'amount',
        'done_orders', 'with_due', 'on_time', 'on_time_rate', 'plan_qty', 'plan_done',
        'plan_rate', 'sent_orders', 'responded', 'response_rate',
    )
    out = {k: (str(kpi[k]) if isinstance(kpi[k], Decimal) else kpi[k]) for k in keep}
    out['weights'] = {key: str(w) for key, _label, w in KPI_WEIGHTS}
    return out


def lock_kpi(*, partner, month: str, user) -> GcKpiSnapshot:
    kpi = partner_kpi(partner, month=month)
    snap, _created = GcKpiSnapshot.objects.update_or_create(
        partner=partner,
        month=kpi['start'],
        defaults={
            'metrics': _jsonable(kpi),
            'score': kpi['score'],
            'grade': kpi['grade'],
            'locked_by': user if getattr(user, 'pk', None) else None,
        },
    )
    return snap


def _dec(raw) -> Decimal | None:
    return None if raw in (None, '') else Decimal(str(raw))


def kpi_for_display(partner, *, month: str = '') -> dict:
    """KPI tháng: bản đã chốt nếu có (``locked``), không thì tạm tính."""
    live = partner_kpi(partner, month=month)
    snap = GcKpiSnapshot.objects.filter(partner=partner, month=live['start']).first()
    if snap is None:
        live.update({'locked': False, 'locked_at': None})
        return live
    m = snap.metrics or {}
    for key in ('reported', 'approved', 'pending_qty', 'amount', 'plan_qty', 'plan_done'):
        live[key] = _dec(m.get(key)) or ZERO
    for key in ('pass_rate', 'on_time_rate', 'plan_rate', 'response_rate'):
        live[key] = _dec(m.get(key))
    for key in ('rejected_n', 'done_orders', 'with_due', 'on_time', 'sent_orders', 'responded'):
        live[key] = int(m.get(key) or 0)
    rate_key = {'quality': 'pass_rate', 'on_time': 'on_time_rate', 'plan': 'plan_rate', 'response': 'response_rate'}
    for row in live['criteria']:
        row['rate'] = live[rate_key[row['key']]]
    live.update({
        'score': snap.score,
        'grade': snap.grade,
        'locked': True,
        'locked_at': snap.locked_at,
        'locked_by': snap.locked_by,
    })
    return live


def current_month() -> str:
    return timezone.localdate().strftime('%Y-%m')
