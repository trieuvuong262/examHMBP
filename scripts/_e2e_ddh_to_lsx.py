"""E2E: ĐĐH nháp → xác nhận → xếp hạng → Chuyển SX (chọn BOM) → LSX.

Chạy trên VPS:
  docker compose exec -T web python manage.py shell < scripts/_e2e_ddh_to_lsx.py
"""

from __future__ import annotations

import sys
import traceback
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from san_xuat.hub_models import SxMoProcessStep, SxProductionOrder, SxSalesOrder
from san_xuat.models import BomVersion, ProductTechDoc
from san_xuat.services.plan_board import (
    QUEUE_STATUSES,
    recompute_plan_ranks,
    release_order_to_production,
)
from san_xuat.services.planning import PlanningError
from san_xuat.services.sales_orders import (
    LineInput,
    confirm_sales_order,
    create_sales_order,
)

FAIL: list[str] = []
PASS: list[str] = []


def ok(msg: str) -> None:
    PASS.append(msg)
    print('PASS:', msg)


def fail(msg: str, detail: str = '') -> None:
    FAIL.append(msg)
    print('FAIL:', msg, detail)


def main() -> int:
    User = get_user_model()
    user = (
        User.objects.filter(is_superuser=True).order_by('id').first()
        or User.objects.filter(is_staff=True).order_by('id').first()
    )
    if not user:
        fail('no staff user')
        return 1

    # --- 0) Tìm mã SP có ≥1 BOM + công đoạn ---
    doc = None
    bom = None
    for d in ProductTechDoc.objects.order_by('-id')[:80]:
        b = (
            BomVersion.objects.filter(tech_doc=d)
            .prefetch_related('process_steps')
            .order_by('-created_at', '-id')
            .first()
        )
        if b and b.process_steps.exists():
            doc, bom = d, b
            break
    if not doc or not bom:
        fail('no ProductTechDoc with BOM+process_steps')
        return 1
    product_code = (doc.product_code or '').strip()
    ok(f'fixture product={product_code} bom=#{bom.pk} label={bom.version_label!r} steps={bom.process_steps.count()}')

    # --- 1) Tạo ĐĐH nháp ---
    today = timezone.localdate()
    order = create_sales_order(
        customer_name='E2E QA Customer',
        request_date=today,
        due_date=today + timedelta(days=14),
        notes='E2E DDH→LSX test — auto cleanup',
        user=user,
        lines=[
            LineInput(
                product_code=product_code,
                product_name=doc.product_name or '',
                qty=Decimal('12'),
            ),
        ],
    )
    ok(f'1.create draft order={order.code} status={order.confirm_status} plan={order.plan_status}')
    if order.confirm_status != SxSalesOrder.CONFIRM_DRAFT:
        fail('draft confirm_status', order.confirm_status)
    if order.lines.count() != 1:
        fail('line count', str(order.lines.count()))

    # --- 2) Xác nhận → hàng đợi ---
    order = confirm_sales_order(order_id=order.pk)
    order.refresh_from_db()
    if order.confirm_status != SxSalesOrder.CONFIRM_CONFIRMED:
        fail('confirm_status', order.confirm_status)
    else:
        ok('2.confirm → confirmed')
    if order.plan_status != SxSalesOrder.PLAN_QUEUED:
        fail('plan_status after confirm', order.plan_status)
    else:
        ok('2.plan_status=queued')
    if not order.plan_queued_at:
        fail('plan_queued_at missing')
    else:
        ok('2.plan_queued_at set')

    # --- 3) Xếp hạng ---
    n = recompute_plan_ranks()
    order.refresh_from_db()
    ok(f'3.recompute_plan_ranks updated={n}')
    if order.plan_status not in (SxSalesOrder.PLAN_RANKED, SxSalesOrder.PLAN_QUEUED):
        # may stay queued if skipped due to existing MO — should be ranked
        fail('unexpected plan_status after rank', order.plan_status)
    else:
        ok(f'3.plan_status={order.plan_status} rank={order.plan_rank} score={order.plan_score}')

    # --- 4a) Release WITHOUT bom → must fail ---
    try:
        release_order_to_production(order_id=order.pk, user=user, bom_by_product={})
        fail('4a.release without bom should raise')
    except PlanningError as exc:
        if 'hồ sơ' in str(exc).lower() or 'bom' in str(exc).lower() or 'chưa chọn' in str(exc).lower():
            ok(f'4a.release without bom blocked: {exc}')
        else:
            fail('4a.wrong error', str(exc))

    # --- 4b) Release with wrong bom id ---
    try:
        release_order_to_production(
            order_id=order.pk,
            user=user,
            bom_by_product={product_code: 999999999},
        )
        fail('4b.release bad bom should raise')
    except PlanningError as exc:
        ok(f'4b.release bad bom blocked: {exc}')

    # --- 4c) Release with correct BOM ---
    created = release_order_to_production(
        order_id=order.pk,
        user=user,
        bom_by_product={product_code: bom.pk},
    )
    if not created:
        fail('4c.no MO created')
    else:
        mo = created[0]
        ok(f'4c.created MO {mo.code} bom={mo.bom_version_id}')
        if mo.bom_version_id != bom.pk:
            fail('4c.bom mismatch', f'got {mo.bom_version_id} want {bom.pk}')
        else:
            ok('4c.MO bom_version matches selected')
        if mo.sales_order_id != order.pk:
            fail('4c.sales_order link', str(mo.sales_order_id))
        else:
            ok('4c.MO linked to sales order')
        steps = list(mo.mo_process_steps.order_by('sequence', 'id'))
        bom_step_names = list(
            bom.process_steps.order_by('sequence', 'id').values_list('process_name', flat=True)
        )
        mo_names = [s.process_name for s in steps]
        if not steps:
            fail('4c.MO has no process steps')
        elif [n.strip().casefold() for n in mo_names] != [n.strip().casefold() for n in bom_step_names]:
            fail('4c.steps mismatch', f'mo={mo_names} bom={bom_step_names}')
        else:
            ok(f'4c.MO process steps from BOM ({len(steps)})')

    order.refresh_from_db()
    if order.plan_status != SxSalesOrder.PLAN_RELEASED:
        fail('4c.order plan_status', order.plan_status)
    else:
        ok('4c.order plan_status=released')

    # --- 4d) Idempotent: release again → no duplicate MO ---
    created2 = release_order_to_production(
        order_id=order.pk,
        user=user,
        bom_by_product={product_code: bom.pk},
    )
    mos = order.production_orders.filter(is_demo=False).exclude(
        status=SxProductionOrder.STATUS_CANCELLED,
    )
    if mos.count() != 1:
        fail('4d.duplicate MO', str(mos.count()))
    else:
        ok('4d.re-release does not duplicate MO')

    # --- 5) HTTP: board GET + release POST with bom_for__ ---
    client = Client(HTTP_HOST='portal.justplay.vn')
    client.force_login(user)

    # New order for HTTP path
    order2 = create_sales_order(
        customer_name='E2E QA HTTP',
        request_date=today,
        due_date=today + timedelta(days=10),
        notes='E2E HTTP release',
        user=user,
        lines=[LineInput(product_code=product_code, qty=Decimal('5'))],
    )
    confirm_sales_order(order_id=order2.pk)
    recompute_plan_ranks()

    r = client.get(reverse('san_xuat:plan_board') + '?mode=list&tab=queue')
    if r.status_code != 200:
        fail('5.board GET', str(r.status_code))
    else:
        body = r.content.decode('utf-8', errors='replace')
        if 'jpReleaseBomModal' not in body:
            fail('5.modal missing in HTML')
        else:
            ok('5.board HTML has release BOM modal')
        if 'data-jp-release-open' not in body:
            fail('5.release button hook missing')
        else:
            ok('5.release open button present')
        if order2.code not in body:
            fail('5.order not on queue board', order2.code)
        else:
            ok(f'5.order {order2.code} visible on queue')

    api = client.get(reverse('san_xuat:mo_bom_versions'), {'product_code': product_code})
    if api.status_code != 200:
        fail('5.bom API', str(api.status_code))
    else:
        data = api.json()
        ids = [x['id'] for x in data.get('results', [])]
        if bom.pk not in ids:
            fail('5.bom API missing fixture bom', str(ids[:5]))
        else:
            ok(f'5.bom API returns {len(ids)} versions')
        steps0 = (data.get('results') or [{}])[-1].get('process_steps') or []
        if not steps0:
            # newest may differ — find our bom
            for row in data.get('results') or []:
                if row.get('id') == bom.pk:
                    steps0 = row.get('process_steps') or []
                    break
        if steps0:
            ok(f'5.bom API includes process_steps ({len(steps0)})')
        else:
            fail('5.bom API process_steps empty for fixture')

    post = client.post(
        reverse('san_xuat:plan_board') + '?mode=list&tab=queue',
        {
            'action': 'release',
            'order_id': str(order2.pk),
            f'bom_for__{product_code}': str(bom.pk),
        },
        follow=False,
    )
    if post.status_code not in (302, 303):
        # may be 200 with error message
        fail('5.HTTP release status', str(post.status_code))
    else:
        ok(f'5.HTTP release redirect {post.status_code}')
    order2.refresh_from_db()
    mo2 = order2.production_orders.filter(is_demo=False).exclude(
        status=SxProductionOrder.STATUS_CANCELLED,
    ).first()
    if not mo2:
        fail('5.HTTP release did not create MO')
    elif mo2.bom_version_id != bom.pk:
        fail('5.HTTP MO bom', str(mo2.bom_version_id))
    else:
        ok(f'5.HTTP MO {mo2.code} bom ok, plan={order2.plan_status}')

    # --- cleanup test orders/MOs ---
    for o in (order, order2):
        o.production_orders.all().delete()
        o.plan_steps.all().delete()
        o.lines.all().delete()
        o.delete()
    ok('cleanup deleted E2E orders')

    print('\n==== SUMMARY ====')
    print(f'PASS {len(PASS)}  FAIL {len(FAIL)}')
    for m in FAIL:
        print(' -', m)
    return 1 if FAIL else 0


try:
    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    traceback.print_exc()
    raise SystemExit(1)
