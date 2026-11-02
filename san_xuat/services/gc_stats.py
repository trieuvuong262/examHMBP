"""Thống kê gia công theo tháng — gom theo đối tác, tổ (công đoạn Ob) hoặc đơn hàng.

Định nghĩa chỉ số (cùng cách tính với ``gc_kpi.partner_kpi``):

- Phiếu / SL đặt / SL nhận / Phí GC: phiếu có ngày lập trong tháng, không tính phiếu hủy.
- SL báo / SL duyệt / tỷ lệ đạt: báo cáo sản lượng có ngày SX trong tháng đã được QC xử lý.
  Tỷ lệ đạt = SL duyệt ÷ SL báo (báo cáo chờ duyệt tính riêng ở cột Chờ duyệt).
- Thành tiền duyệt = Σ SL duyệt × đơn giá phiếu.
- Đúng hạn: phiếu nhận lại / hoàn thành trong tháng có hạn, ngày nhận ≤ hạn.
"""

from __future__ import annotations

from decimal import Decimal

from san_xuat.hub_models import SxSubcontractOrder
from san_xuat.partner_models import GcOutputReport
from san_xuat.services.gc_kpi import _month_range

ZERO = Decimal('0')

GROUP_PARTNER = 'partner'
GROUP_TEAM = 'team'
GROUP_ORDER = 'order'
GROUP_CHOICES = (
    (GROUP_PARTNER, 'Theo đối tác'),
    (GROUP_TEAM, 'Theo tổ / công đoạn'),
    (GROUP_ORDER, 'Theo đơn hàng'),
)
_GROUP_KEYS = {key for key, _label in GROUP_CHOICES}

_DONE_STATUSES = (SxSubcontractOrder.STATUS_RECEIVED, SxSubcontractOrder.STATUS_DONE)


def normalize_group(raw: str) -> str:
    value = (raw or '').strip().lower()
    return value if value in _GROUP_KEYS else GROUP_PARTNER


def _group_of(order: SxSubcontractOrder, group_by: str) -> tuple[tuple, str, dict]:
    """(khóa gom, nhãn, thông tin link) của một phiếu GC."""
    if group_by == GROUP_TEAM:
        slug = (order.team_slug or '').strip().lower()
        return ('team', slug), (order.team_label or slug or '—'), {'team': slug}
    if group_by == GROUP_ORDER:
        if order.sales_order_id:
            code = order.sales_order.code
            return ('so', order.sales_order_id), code, {'q': code}
        if order.production_order_id:
            code = order.production_order.code
            return ('mo', order.production_order_id), code, {'q': code}
        return ('none', 0), 'Không gắn đơn hàng', {}
    if order.partner_id:
        return ('partner', order.partner_id), order.partner.name, {'partner_id': order.partner_id}
    vendor = (order.vendor_name or '').strip() or '—'
    return ('vendor', vendor.casefold()), vendor, {'q': vendor if vendor != '—' else ''}


def _new_row(label: str, link: dict) -> dict:
    return {
        'label': label,
        'link': link,
        'orders': 0,
        'qty': ZERO,
        'qty_received': ZERO,
        'service_fee': ZERO,
        'reported': ZERO,
        'approved': ZERO,
        'pending_qty': ZERO,
        'rejected_n': 0,
        'amount': ZERO,
        'done_orders': 0,
        'with_due': 0,
        'on_time': 0,
    }


def _finish(row: dict) -> dict:
    reported = row['reported']
    row['pass_rate'] = (
        (row['approved'] * 100 / reported).quantize(Decimal('0.1')) if reported else None
    )
    row['on_time_rate'] = (
        (Decimal(row['on_time']) * 100 / row['with_due']).quantize(Decimal('0.1'))
        if row['with_due'] else None
    )
    row['amount'] = row['amount'].quantize(Decimal('1'))
    return row


def build_gc_stats(*, month: str = '', group_by: str = GROUP_PARTNER) -> dict:
    group_by = normalize_group(group_by)
    start, end, month_value = _month_range(month)
    rows: dict[tuple, dict] = {}

    def _row_for(order: SxSubcontractOrder) -> dict:
        key, label, link = _group_of(order, group_by)
        row = rows.get(key)
        if row is None:
            row = rows[key] = _new_row(label, link)
        return row

    related = ('partner', 'sales_order', 'production_order')
    orders = (
        SxSubcontractOrder.objects.filter(is_demo=False, order_date__range=(start, end))
        .exclude(status=SxSubcontractOrder.STATUS_CANCELLED)
        .select_related(*related)
    )
    for order in orders:
        row = _row_for(order)
        row['orders'] += 1
        row['qty'] += order.qty or ZERO
        row['qty_received'] += order.qty_received or ZERO
        row['service_fee'] += order.service_fee or ZERO

    reports = (
        GcOutputReport.objects.filter(work_date__range=(start, end), order__is_demo=False)
        .exclude(status=GcOutputReport.STATUS_CANCELLED)
        .select_related(*(f'order__{name}' for name in related))
    )
    for report in reports:
        row = _row_for(report.order)
        if report.status == GcOutputReport.STATUS_SUBMITTED:
            row['pending_qty'] += report.total_qty or ZERO
            continue
        row['reported'] += report.total_qty or ZERO
        if report.status == GcOutputReport.STATUS_REJECTED:
            row['rejected_n'] += 1
            continue
        approved = report.approved_qty or ZERO
        row['approved'] += approved
        row['amount'] += approved * (report.order.unit_price or ZERO)

    done = (
        SxSubcontractOrder.objects.filter(
            is_demo=False,
            status__in=_DONE_STATUSES,
            received_at__date__range=(start, end),
        )
        .select_related(*related)
    )
    for order in done:
        row = _row_for(order)
        row['done_orders'] += 1
        if order.due_date:
            row['with_due'] += 1
            if order.received_at and order.received_at.date() <= order.due_date:
                row['on_time'] += 1

    total = _new_row('Tổng cộng', {})
    for row in rows.values():
        for field, value in row.items():
            if field in ('label', 'link'):
                continue
            total[field] += value
    result_rows = sorted(
        (_finish(row) for row in rows.values()),
        key=lambda r: (-r['qty'], -r['approved'], r['label'].casefold()),
    )
    return {
        'month_value': month_value,
        'start': start,
        'end': end,
        'group_by': group_by,
        'rows': result_rows,
        'total': _finish(total),
    }
