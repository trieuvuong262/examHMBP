"""Gắn phiếu xuất Kho NPL với đơn hàng và một tổ trên lộ trình."""

from __future__ import annotations

from decimal import Decimal

_OPEN_MO_RANK = {
    'in_progress': 0,
    'released': 1,
    'draft': 2,
}


def work_center_recipient_label(work_center) -> str:
    if work_center is None:
        return ''
    return ((work_center.team_label or work_center.name or work_center.code) or '').strip()[:120]


def _order_product(order) -> tuple[str, str]:
    lines = list(order.lines.all())
    if not lines:
        return '', ''
    line = min(lines, key=lambda row: row.pk)
    return (line.product_code or '').strip(), (line.product_name or '').strip()


def sales_order_option_text(order) -> str:
    code = (getattr(order, 'code', None) or '').strip()
    product_code, product_name = _order_product(order)
    product = product_name or product_code
    bits = [bit for bit in (product, code) if bit]
    return ' · '.join(bits)


def sales_order_search_row(order, galleries: dict | None = None) -> dict:
    code = (getattr(order, 'code', None) or '').strip()
    customer = (getattr(order, 'customer_name', None) or '').strip()
    product_code, product_name = _order_product(order)
    product = product_name or product_code
    image_url = ''
    if product_code and galleries is not None:
        urls = galleries.get(product_code.casefold()) or []
        image_url = urls[0] if urls else ''
    bits = [bit for bit in (product, code) if bit]
    return {
        'id': str(order.pk),
        'text': ' · '.join(bits),
        'code': code,
        'name': product,
        'customer': customer,
        'image_url': image_url,
    }


def search_route_sales_orders(query: str, *, limit: int = 40) -> list[dict]:
    from django.db.models import Q

    from san_xuat.hub_models import SxSalesOrder

    qs = (
        SxSalesOrder.objects.filter(is_demo=False)
        .exclude(plan_status=SxSalesOrder.PLAN_CANCELLED)
        .exclude(confirm_status=SxSalesOrder.CONFIRM_REJECTED)
    )
    text = (query or '').strip()
    if text:
        qs = qs.filter(
            Q(code__icontains=text)
            | Q(customer_name__icontains=text)
            | Q(lines__product_code__icontains=text)
            | Q(lines__product_name__icontains=text)
        )
    orders = list(
        qs.distinct().order_by('-request_date', '-id').prefetch_related('lines')[:limit]
    )
    from san_xuat.services.products import product_gallery_map

    galleries = product_gallery_map(
        product_code for order in orders for product_code, _name in (_order_product(order),)
    )
    return [sales_order_search_row(order, galleries) for order in orders]


def route_teams_for_order(order) -> list[dict]:
    """Một dòng cho mỗi tổ đang có trên lộ trình của đơn."""
    if order is None or not getattr(order, 'pk', None):
        return []
    grouped: dict[int, dict] = {}
    steps = order.plan_steps.select_related('work_center').order_by('sequence', 'id')
    for step in steps:
        if not step.work_center_id:
            continue
        bucket = grouped.setdefault(step.work_center_id, {
            'wc': step.work_center,
            'sequence': step.sequence,
        })
        bucket['sequence'] = min(bucket['sequence'], step.sequence)
    day_rows = order.team_day_plans.select_related('work_center').filter(work_center__isnull=False)
    for row in day_rows:
        if row.work_center_id in grouped:
            continue
        grouped[row.work_center_id] = {
            'wc': row.work_center,
            'sequence': 1000,
        }
    results = []
    for wc_id, bucket in sorted(grouped.items(), key=lambda item: (item[1]['sequence'], item[0])):
        text = work_center_recipient_label(bucket['wc']) or str(wc_id)
        results.append({'id': str(wc_id), 'text': text})
    return results


def sales_order_bom_qty_caps(order) -> dict[int, Decimal]:
    """NPL thuộc BOM đơn → tổng SL định mức. Danh sách xuất lấy các mã này, không chặn vượt SL."""
    from django.db.models.functions import Lower

    from kho_npl.models import Material
    from san_xuat.services.bom_need import explode_for_sales_line

    if order is None or not getattr(order, 'pk', None):
        return {}
    totals: dict[str, Decimal] = {}
    for line in order.lines.select_related('bom_version').all():
        for need in explode_for_sales_line(line):
            code = (need.material_code or '').strip().casefold()
            if not code or need.qty_total <= 0:
                continue
            totals[code] = totals.get(code, Decimal('0')) + need.qty_total
    if not totals:
        return {}
    caps: dict[int, Decimal] = {}
    materials = Material.objects.annotate(code_key=Lower('code')).filter(
        is_active=True,
        code_key__in=list(totals),
    )
    for material in materials:
        caps[material.pk] = totals.get(material.code.casefold(), Decimal('0'))
    return caps


def open_production_order(order):
    """Lệnh đang mở của đơn: đang SX, rồi đã phát hành, rồi nháp. Lấy lệnh mới hơn nếu cùng trạng thái."""
    if order is None or not getattr(order, 'pk', None):
        return None
    from san_xuat.hub_models import SxProductionOrder

    mos = list(
        order.production_orders.filter(
            is_demo=False,
            status__in=(
                SxProductionOrder.STATUS_IN_PROGRESS,
                SxProductionOrder.STATUS_RELEASED,
                SxProductionOrder.STATUS_DRAFT,
            ),
        )
    )
    if not mos:
        return None
    mos.sort(key=lambda mo: (_OPEN_MO_RANK.get(mo.status, 9), -mo.pk))
    return mos[0]


def stamp_route_link(issue, *, sales_order, work_center, production_order_code=None, unlink=False):
    """Ghi đơn, tổ và lệnh đang mở lên phiếu. `unlink` xóa liên kết lộ trình."""
    if unlink:
        issue.sales_order = None
        issue.work_center = None
        issue.production_order = ''
        issue.recipient_department = ''
        return issue
    issue.sales_order = sales_order
    issue.work_center = work_center
    if production_order_code is None:
        mo = open_production_order(sales_order)
        if mo is not None:
            production_order_code = mo.code
        else:
            existing = (issue.production_order or '').strip()
            belongs = bool(existing and sales_order) and sales_order.production_orders.filter(
                code=existing,
                is_demo=False,
            ).exists()
            production_order_code = existing if belongs else ''
    issue.production_order = (production_order_code or '')[:60]
    issue.recipient_department = work_center_recipient_label(work_center)
    return issue
