"""Seed demo phiếu tiến độ (ĐĐH + LSX size + vài SL) — chạy trên VPS."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from san_xuat.hub_models import (
    SxProductionOrder,
    SxProductionOrderLine,
    SxSalesOrder,
    SxSalesOrderLine,
)
from san_xuat.services.dispatch import _code
from san_xuat.services.order_progress_sheet import (
    ensure_progress_work_centers,
    record_progress_qty,
    seed_order_plan_steps_from_template,
)
from san_xuat.services.products import resolve_product_ref, search_products

DEMO_SO = 'DH-DEMO-TD-001'
DEMO_MO = 'LSX-DEMO-TD-001'
DEMO_NOTE = '[DEMO phiếu tiến độ]'

# Size như Excel: 650
SIZE_QTY = [
    ('S', Decimal('100')),
    ('M', Decimal('150')),
    ('L', Decimal('150')),
    ('XL', Decimal('150')),
    ('2XL', Decimal('100')),
]


def _pick_product() -> tuple[str, str]:
    ref = resolve_product_ref('JP') or resolve_product_ref('SP')
    if ref:
        return ref.code, (ref.name or '').strip()
    rows = search_products('', limit=5)
    if rows:
        return rows[0]['code'], (rows[0].get('name') or '').strip()
    return 'DEMO-TEE-001', 'Pháp xanh đen 2026 - TAY DÀI'


@transaction.atomic
def run():
    ensure_progress_work_centers()
    today = timezone.localdate()
    product_code, product_name = _pick_product()
    product_name = 'Pháp xanh đen 2026 - TAY DÀI'

    # Xóa demo cũ cùng mã
    SxProductionOrder.objects.filter(code=DEMO_MO).delete()
    SxSalesOrder.objects.filter(code=DEMO_SO).delete()

    total = sum((q for _, q in SIZE_QTY), Decimal('0'))
    so = SxSalesOrder.objects.create(
        code=DEMO_SO,
        customer_name='Khách demo JustPlay',
        request_date=today,
        due_date=today + timedelta(days=21),
        confirm_status=SxSalesOrder.CONFIRM_CONFIRMED,
        plan_status=SxSalesOrder.PLAN_RELEASED,
        plan_priority=SxSalesOrder.PRIORITY_HIGH,
        plan_rank=1,
        plan_queued_at=timezone.now(),
        notes=DEMO_NOTE,
        is_demo=False,
    )
    SxSalesOrderLine.objects.create(
        order=so,
        product_code=product_code,
        product_name=product_name,
        qty=total,
        sort_order=10,
    )
    seed_order_plan_steps_from_template(so)

    mo = SxProductionOrder.objects.create(
        code=DEMO_MO,
        product_code=product_code,
        product_name=product_name,
        qty=total,
        order_date=today,
        due_date=today + timedelta(days=21),
        status=SxProductionOrder.STATUS_IN_PROGRESS,
        sales_order=so,
        notes=DEMO_NOTE,
        is_demo=False,
    )
    for size, qty in SIZE_QTY:
        SxProductionOrderLine.objects.create(
            production_order=mo,
            size_label=size,
            color_label='Xanh đen',
            color_code='NVY',
            qty=qty,
            sku_code=f'{product_code}-NVY-{size}',
        )

    # Cắt: đủ size; IN-ÉP lá cổ một phần
    for size, qty in SIZE_QTY:
        record_progress_qty(
            mo_id=mo.pk,
            process_key='cat_ao',
            size_label=size,
            qty=qty,
            stat_date=today - timedelta(days=1),
        )
    record_progress_qty(
        mo_id=mo.pk,
        process_key='inep_la_co',
        size_label='M',
        qty=Decimal('80'),
        stat_date=today,
    )
    record_progress_qty(
        mo_id=mo.pk,
        process_key='inep_la_co',
        size_label='L',
        qty=Decimal('50'),
        stat_date=today,
    )

    print('OK')
    print('so', so.pk, so.code)
    print('mo', mo.pk, mo.code, mo.product_code)
    print('total', total)
    print('sheet_url', f'/san-xuat/ke-hoach/tien-do/{mo.pk}/')
    print('board_url', '/san-xuat/ke-hoach/bang/?mode=list&tab=released')
    print('mo_url', f'/san-xuat/dieu-phoi/lenh-sx/{mo.pk}/')


run()
