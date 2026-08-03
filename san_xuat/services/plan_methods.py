"""Ba phương án lập kế hoạch sản xuất: MTO, MTS, MPS.

Mỗi phương án có một cách nạp nhu cầu vào Kế hoạch tổng thể (KHTT):

  MTO  nhu cầu = dòng hàng của các đơn đặt hàng KiotViet đã chọn
  MTS  nhu cầu = bù tồn theo chính sách tồn thành phẩm (min/max stock)
  MPS  nhu cầu = nhập tay hoặc gộp từ MTO+MTS, chia theo kỳ tuần/tháng

Cả 3 đều đi qua netting chung (trừ tồn TP khả dụng và hàng đang sản xuất)
rồi ghi vào ``SxOverallPlanLine``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from san_xuat.hub_models import (
    SxOverallPlan,
    SxOverallPlanLine,
    SxProductStockPolicy,
)
from san_xuat.services.demand import (
    DemandItem,
    apply_netting,
    build_restock_suggestions,
    merge_by_product,
)
from san_xuat.services.planning import PlanningError, _resolve_product_name

_Q = Decimal('0.01')


def _q(value) -> Decimal:
    return (Decimal(str(value or 0))).quantize(_Q)


def _require_draft(plan: SxOverallPlan) -> None:
    if plan.status != SxOverallPlan.STATUS_DRAFT:
        raise PlanningError('Chỉ nạp nhu cầu khi KHTT đang nháp.')


def _assert_method(plan: SxOverallPlan, expected: str, label: str) -> None:
    if plan.plan_method != expected:
        raise PlanningError(
            f'KHTT {plan.code} đang dùng phương án '
            f'«{plan.get_plan_method_display()}» — không nạp được nhu cầu {label}.'
        )


# ---------------------------------------------------------------------------
# Ghi dòng KHTT từ danh sách nhu cầu đã netting
# ---------------------------------------------------------------------------

def _write_lines(
    plan: SxOverallPlan,
    items: list[DemandItem],
    *,
    replace: bool = True,
    skip_covered: bool = True,
) -> int:
    if replace:
        plan.lines.all().delete()

    rows: list[SxOverallPlanLine] = []
    for item in items:
        if skip_covered and item.qty_net <= 0:
            continue
        rows.append(
            SxOverallPlanLine(
                plan=plan,
                product_code=item.product_code,
                product_name=item.product_name or _resolve_product_name(item.product_code),
                qty_required=_q(item.qty_gross),
                qty_planned=_q(item.qty_net if plan.apply_netting else item.qty_gross),
                qty_gross=_q(item.qty_gross),
                qty_on_hand=_q(item.qty_on_hand),
                qty_wip=_q(item.qty_wip),
                due_date=item.due_date,
                kv_order_code=(item.kv_order_code or '')[:64],
                kv_order_kiotviet_id=item.kv_order_kiotviet_id,
            )
        )
    if rows:
        SxOverallPlanLine.objects.bulk_create(rows)
    return len(rows)


# ---------------------------------------------------------------------------
# MTO — sản xuất theo đơn đặt hàng
# ---------------------------------------------------------------------------

@dataclass
class KvOrderOption:
    kiotviet_id: int
    code: str
    customer_name: str
    purchase_date: object
    line_count: int
    total_qty: Decimal


def list_open_kv_orders(*, limit: int = 200, search: str = '') -> list[KvOrderOption]:
    """Đơn đặt hàng KiotViet có thể đưa vào kế hoạch."""
    try:
        from kiotviet.models import KvOrder, KvOrderLine
        from kiotviet.sync_service import current_retailer
    except Exception:
        return []

    retailer = current_retailer()
    qs = KvOrder.objects.filter(retailer=retailer)
    term = (search or '').strip()
    if term:
        from django.db.models import Q

        qs = qs.filter(Q(code__icontains=term) | Q(customer_name__icontains=term))
    orders = list(qs.order_by('-purchase_date', '-kiotviet_id')[:limit])
    if not orders:
        return []

    order_ids = [o.kiotviet_id for o in orders]
    agg: dict[int, list] = {}
    for row in KvOrderLine.objects.filter(
        retailer=retailer, order_kiotviet_id__in=order_ids,
    ).values_list('order_kiotviet_id', 'quantity'):
        oid, qty = row
        cur = agg.setdefault(int(oid), [0, Decimal('0')])
        cur[0] += 1
        cur[1] += _q(qty)

    out: list[KvOrderOption] = []
    for o in orders:
        count, total = agg.get(o.kiotviet_id, [0, Decimal('0')])
        if count == 0:
            continue
        out.append(
            KvOrderOption(
                kiotviet_id=o.kiotviet_id,
                code=o.code or str(o.kiotviet_id),
                customer_name=getattr(o, 'customer_name', '') or '',
                purchase_date=getattr(o, 'purchase_date', None),
                line_count=count,
                total_qty=total,
            )
        )
    return out


def collect_mto_demand(
    *,
    kv_order_ids: list[int],
    due_date=None,
) -> list[DemandItem]:
    """Gom dòng hàng của nhiều đơn KV thành nhu cầu theo mã SP."""
    ids = [int(x) for x in (kv_order_ids or []) if str(x).strip().isdigit()]
    if not ids:
        raise PlanningError('Chưa chọn đơn đặt hàng nào.')
    try:
        from kiotviet.models import KvOrder, KvOrderLine
        from kiotviet.sync_service import current_retailer
    except Exception as exc:
        raise PlanningError('Chưa cấu hình kết nối KiotViet.') from exc

    retailer = current_retailer()
    order_map = {
        o.kiotviet_id: o
        for o in KvOrder.objects.filter(retailer=retailer, kiotviet_id__in=ids)
    }
    missing = [str(i) for i in ids if i not in order_map]
    if missing:
        raise PlanningError(f'Không tìm thấy đơn KV: {", ".join(missing)}.')

    items: list[DemandItem] = []
    for line in KvOrderLine.objects.filter(
        retailer=retailer, order_kiotviet_id__in=ids,
    ).order_by('order_kiotviet_id', 'id'):
        code = (line.product_code or '').strip()
        qty = _q(line.quantity)
        if not code or qty <= 0:
            continue
        order = order_map.get(int(line.order_kiotviet_id))
        order_due = due_date
        if order_due is None and order is not None:
            pd = getattr(order, 'purchase_date', None)
            order_due = pd.date() if hasattr(pd, 'date') else pd
        items.append(
            DemandItem(
                product_code=code,
                product_name=(line.product_name or '').strip()[:255],
                qty_gross=qty,
                due_date=order_due,
                kv_order_code=(order.code if order else '') or '',
                kv_order_kiotviet_id=int(line.order_kiotviet_id),
            )
        )
    if not items:
        raise PlanningError('Các đơn đã chọn không có dòng hàng hợp lệ.')
    return items


@transaction.atomic
def load_mto_demand(
    *,
    plan_id: int,
    kv_order_ids: list[int],
    replace: bool = True,
) -> dict:
    """Nạp nhu cầu MTO vào KHTT (gộp theo mã SP + netting)."""
    plan = SxOverallPlan.objects.select_for_update().get(pk=plan_id)
    _require_draft(plan)
    _assert_method(plan, SxOverallPlan.METHOD_MTO, 'theo đơn đặt hàng')

    raw = collect_mto_demand(kv_order_ids=kv_order_ids)
    merged = merge_by_product(raw)
    netted = apply_netting(merged, enabled=plan.apply_netting)
    written = _write_lines(plan, netted, replace=replace)

    covered = [it for it in netted if it.is_covered]
    if plan.source != SxOverallPlan.SOURCE_SALES_ORDER:
        plan.source = SxOverallPlan.SOURCE_SALES_ORDER
        plan.save(update_fields=['source'])
    return {
        'written': written,
        'total_items': len(netted),
        'covered': len(covered),
        'covered_codes': [it.product_code for it in covered],
    }


# ---------------------------------------------------------------------------
# MTS — sản xuất bù tồn kho
# ---------------------------------------------------------------------------

@transaction.atomic
def load_mts_demand(
    *,
    plan_id: int,
    product_codes: list[str] | None = None,
    replace: bool = True,
) -> dict:
    """Nạp nhu cầu MTS: các mã SP có tồn dưới mức tối thiểu.

    ``product_codes`` = giới hạn ở các mã được chọn; None = lấy tất cả mã thiếu.
    """
    plan = SxOverallPlan.objects.select_for_update().get(pk=plan_id)
    _require_draft(plan)
    _assert_method(plan, SxOverallPlan.METHOD_MTS, 'bù tồn kho')

    suggestions = build_restock_suggestions()
    if product_codes:
        wanted = {(c or '').strip().upper() for c in product_codes if (c or '').strip()}
        suggestions = [
            s for s in suggestions if (s.policy.product_code or '').strip().upper() in wanted
        ]
    if not suggestions:
        raise PlanningError(
            'Không có mã sản phẩm nào dưới mức tồn tối thiểu. '
            'Khai báo chính sách tồn thành phẩm trước.'
        )

    # SL đề xuất đã trừ tồn + WIP nên không netting lần hai
    items = [
        DemandItem(
            product_code=s.policy.product_code,
            product_name=s.policy.product_name,
            qty_gross=s.qty_suggest,
            qty_on_hand=s.qty_on_hand,
            qty_wip=s.qty_wip,
            qty_net=s.qty_suggest,
            due_date=(
                timezone.localdate() + timedelta(days=s.policy.lead_time_days)
                if s.policy.lead_time_days
                else None
            ),
            note='Bù tồn',
        )
        for s in suggestions
    ]
    written = _write_lines(plan, items, replace=replace)
    return {'written': written, 'total_items': len(items), 'covered': 0, 'covered_codes': []}


# ---------------------------------------------------------------------------
# MPS — lịch trình chủ theo kỳ
# ---------------------------------------------------------------------------

def bucket_start_for(day: date, bucket: str) -> date:
    """Mốc đầu kỳ của một ngày theo chu kỳ lịch trình."""
    if bucket == SxOverallPlan.BUCKET_MONTH:
        return day.replace(day=1)
    if bucket == SxOverallPlan.BUCKET_WEEK:
        return day - timedelta(days=day.weekday())
    return day


def mps_buckets(plan: SxOverallPlan) -> list[dict]:
    """Danh sách kỳ lịch trình trong khoảng KHTT."""
    if not plan.date_from or not plan.date_to or plan.date_from > plan.date_to:
        return []
    bucket = plan.mps_bucket or SxOverallPlan.BUCKET_WEEK
    out: list[dict] = []
    seen: set[date] = set()
    day = plan.date_from
    while day <= plan.date_to:
        start = bucket_start_for(day, bucket)
        if start not in seen:
            seen.add(start)
            if bucket == SxOverallPlan.BUCKET_MONTH:
                nxt = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
                end = nxt - timedelta(days=1)
                label = start.strftime('T%m/%Y')
            elif bucket == SxOverallPlan.BUCKET_WEEK:
                end = start + timedelta(days=6)
                label = f'Tuần {start:%d/%m}'
            else:
                end = start
                label = start.strftime('%d/%m')
            out.append({
                'start': start,
                'end': min(end, plan.date_to) if end > plan.date_to else end,
                'label': label,
                'is_frozen': is_bucket_frozen(plan, start),
            })
        day += timedelta(days=1)
    return out


def is_bucket_frozen(plan: SxOverallPlan, bucket_start: date | None) -> bool:
    """Kỳ đã đóng băng — không cho sửa sản lượng."""
    if not plan.frozen_until or not bucket_start:
        return False
    return bucket_start <= plan.frozen_until


@transaction.atomic
def load_mps_demand(
    *,
    plan_id: int,
    rows: list[dict],
    replace: bool = False,
) -> dict:
    """Nạp/cập nhật lịch trình chủ.

    ``rows`` = [{'product_code', 'qty', 'bucket_start'(YYYY-MM-DD|date), 'product_name'?}]
    Kỳ đã đóng băng bị bỏ qua (không ghi đè).
    """
    from datetime import datetime

    plan = SxOverallPlan.objects.select_for_update().get(pk=plan_id)
    _require_draft(plan)
    _assert_method(plan, SxOverallPlan.METHOD_MPS, 'lịch trình chủ')

    def _to_date(raw):
        if isinstance(raw, date):
            return raw
        text = (str(raw or '')).strip()
        if not text:
            return None
        try:
            return datetime.strptime(text, '%Y-%m-%d').date()
        except ValueError:
            return None

    if replace:
        plan.lines.exclude(
            bucket_start__lte=plan.frozen_until,
        ).delete() if plan.frozen_until else plan.lines.all().delete()

    bucket = plan.mps_bucket or SxOverallPlan.BUCKET_WEEK
    written = 0
    frozen_skipped = 0
    for row in rows or []:
        code = (str(row.get('product_code') or '')).strip()
        qty = _q(row.get('qty'))
        start = _to_date(row.get('bucket_start')) or plan.date_from
        if not code or qty <= 0:
            continue
        start = bucket_start_for(start, bucket)
        if is_bucket_frozen(plan, start):
            frozen_skipped += 1
            continue
        line = plan.lines.filter(product_code__iexact=code, bucket_start=start).first()
        if line is None:
            line = SxOverallPlanLine(plan=plan, product_code=code, bucket_start=start)
        line.product_name = (
            (str(row.get('product_name') or '')).strip() or _resolve_product_name(code)
        )
        line.qty_gross = qty
        line.qty_required = qty
        line.qty_planned = qty
        line.save()
        written += 1

    # Netting sau khi có toàn bộ dòng — trừ tồn cho kỳ sớm nhất trước
    if plan.apply_netting:
        recompute_plan_netting(plan_id=plan.pk)
    return {'written': written, 'frozen_skipped': frozen_skipped}


# ---------------------------------------------------------------------------
# Tính lại netting cho KHTT hiện có
# ---------------------------------------------------------------------------

@transaction.atomic
def recompute_plan_netting(*, plan_id: int) -> dict:
    """Tính lại tồn/WIP và nhu cầu thực cho toàn bộ dòng KHTT."""
    plan = SxOverallPlan.objects.select_for_update().prefetch_related('lines').get(pk=plan_id)
    if plan.status not in (SxOverallPlan.STATUS_DRAFT, SxOverallPlan.STATUS_CONFIRMED):
        raise PlanningError('Chỉ tính lại nhu cầu khi KHTT còn nháp hoặc đã xác nhận.')

    lines = list(plan.lines.all())
    if not lines:
        return {'updated': 0, 'covered': 0}

    items = [
        DemandItem(
            product_code=ln.product_code,
            product_name=ln.product_name,
            qty_gross=_q(ln.qty_gross or ln.qty_required or ln.qty_planned),
            due_date=ln.due_date or ln.bucket_start,
        )
        for ln in lines
    ]
    apply_netting(items, enabled=plan.apply_netting)

    covered = 0
    for ln, item in zip(lines, items):
        ln.qty_gross = item.qty_gross
        ln.qty_on_hand = item.qty_on_hand
        ln.qty_wip = item.qty_wip
        ln.qty_planned = item.qty_net if plan.apply_netting else item.qty_gross
        if item.is_covered:
            covered += 1
    SxOverallPlanLine.objects.bulk_update(
        lines, ['qty_gross', 'qty_on_hand', 'qty_wip', 'qty_planned'],
    )
    return {'updated': len(lines), 'covered': covered}


# ---------------------------------------------------------------------------
# Chính sách tồn thành phẩm
# ---------------------------------------------------------------------------

@transaction.atomic
def upsert_stock_policy(
    *,
    product_code: str,
    min_stock: Decimal,
    max_stock: Decimal | None = None,
    lead_time_days: int = 0,
    product_name: str = '',
    is_active: bool = True,
) -> SxProductStockPolicy:
    code = (product_code or '').strip()
    if not code:
        raise PlanningError('Thiếu mã sản phẩm.')
    if (min_stock or Decimal('0')) < 0:
        raise PlanningError('Tồn tối thiểu không được âm.')
    target = max_stock or Decimal('0')
    if target and target < min_stock:
        raise PlanningError('Tồn mục tiêu phải lớn hơn hoặc bằng tồn tối thiểu.')

    policy, _created = SxProductStockPolicy.objects.update_or_create(
        product_code=code,
        defaults={
            'product_name': (product_name or '').strip() or _resolve_product_name(code),
            'min_stock': _q(min_stock),
            'max_stock': _q(target),
            'lead_time_days': max(0, int(lead_time_days or 0)),
            'is_active': bool(is_active),
            'is_demo': False,
        },
    )
    return policy
