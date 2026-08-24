"""E2E: ĐĐH + routing SMV áp dụng → xác nhận → GTKH theo đơn → xếp hạng → LSX.

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

from san_xuat.hub_models import SxMoProcessStep, SxOrderPlanCost, SxProductionOrder, SxSalesOrder
from san_xuat.ie_models import SxOperation, SxOperationGroup, SxRouting, SxRoutingLine
from san_xuat.models import BomVersion, ProductTechDoc
from san_xuat.services.costing import compute_costing, compute_costing_for_sales_line
from san_xuat.services.order_routing import routings_for_product
from san_xuat.services.plan_costing import build_order_sheet_from_kv
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


def _ensure_routing(doc, bom) -> SxRouting:
    code = (doc.product_code or '').strip()
    for routing in routings_for_product(code):
        if routing.lines.filter(applied_unit_smv__gt=0).exists():
            return routing
    op = (
        SxOperation.objects.filter(status=SxOperation.STATUS_APPROVED).order_by('id').first()
        or SxOperation.objects.order_by('id').first()
    )
    if op is None:
        grp = SxOperationGroup.objects.order_by('id').first()
        if grp is None:
            grp = SxOperationGroup.objects.create(code='E2E', name='E2E workflow')
        op = SxOperation.objects.create(
            group=grp,
            op_code='E2E-9001',
            op_rev='R01',
            name_vi='E2E May',
            base_smv_min=Decimal('1.5000'),
            status=SxOperation.STATUS_APPROVED,
        )
    rid = f'E2E-{code}-R01'[:80]
    routing, _created = SxRouting.objects.get_or_create(
        routing_id=rid,
        defaults={
            'style_code': code,
            'style_name': doc.product_name or '',
            'routing_rev': 'R01',
            'tech_doc': doc,
            'is_active': True,
            'approval_status': SxRouting.APPROVAL_APPROVED,
            'notes': 'E2E auto routing',
        },
    )
    if not routing.lines.filter(applied_unit_smv__gt=0).exists():
        smv = op.base_smv_min or Decimal('1.5000')
        factor = Decimal('1000')
        SxRoutingLine.objects.create(
            routing=routing,
            seq_no=10,
            operation=op,
            op_code=op.op_code,
            op_rev=op.op_rev,
            op_name_vi=op.name_vi,
            library_unit_smv=smv,
            applied_unit_smv=smv,
            qty_per_garment=Decimal('1'),
            price_factor=factor,
            total_unit_price=(smv * factor).quantize(Decimal('0.01')),
        )
    return routing


def main() -> int:
    User = get_user_model()
    user = (
        User.objects.filter(is_superuser=True).order_by('id').first()
        or User.objects.filter(is_staff=True).order_by('id').first()
    )
    if not user:
        fail('no staff user')
        return 1

    # --- 0) Tìm mã SP có BOM; gắn routing (có sẵn hoặc E2E) ---
    doc = None
    bom = None
    for d in ProductTechDoc.objects.order_by('-id')[:80]:
        b = (
            BomVersion.objects.filter(tech_doc=d)
            .prefetch_related('process_steps')
            .order_by('-created_at', '-id')
            .first()
        )
        if b:
            doc, bom = d, b
            if b.process_steps.exists():
                break
    if not doc or not bom:
        fail('no ProductTechDoc with BOM')
        return 1
    product_code = (doc.product_code or '').strip()
    routing = _ensure_routing(doc, bom)
    ok(
        f'fixture product={product_code} bom=#{bom.pk} routing={routing.routing_id} '
        f'ops={routing.lines.count()} smv={routing.total_smv}'
    )

    # --- 1) Tạo ĐĐH nháp (BOM + routing) ---
    today = timezone.localdate()
    order = create_sales_order(
        customer_name='E2E QA Customer',
        request_date=today,
        due_date=today + timedelta(days=14),
        notes='E2E DDH→routing→GTKH→LSX — auto cleanup',
        user=user,
        lines=[
            LineInput(
                product_code=product_code,
                product_name=doc.product_name or '',
                qty=Decimal('12'),
                routing_id=routing.pk,
            ),
        ],
    )
    ok(f'1.create draft order={order.code} status={order.confirm_status} plan={order.plan_status}')
    if order.confirm_status != SxSalesOrder.CONFIRM_DRAFT:
        fail('draft confirm_status', order.confirm_status)
    so_line = order.lines.get()
    if so_line.routing_id != routing.pk:
        fail('1.line routing', str(so_line.routing_id))
    else:
        ok('1.line has routing')
    snaps = list(so_line.routing_lines.order_by('seq_no', 'id'))
    if not snaps:
        fail('1.snapshot empty')
    else:
        ok(f'1.snapshot {len(snaps)} CĐ SMV áp dụng={snaps[0].applied_unit_smv}')

    # --- 1b) Xác nhận không BOM/OB vẫn được (chọn sau khi chuyển SX) ---
    bare = create_sales_order(
        customer_name='E2E no routing',
        request_date=today,
        lines=[LineInput(product_code=product_code, qty=Decimal('1'))],
        user=user,
    )
    try:
        confirm_sales_order(order_id=bare.pk)
        bare.refresh_from_db()
        if bare.confirm_status == SxSalesOrder.CONFIRM_CONFIRMED:
            ok('1b.confirm without BOM/OB allowed')
        else:
            fail('1b.confirm without BOM/OB status', bare.confirm_status)
    except PlanningError as exc:
        fail('1b.confirm without BOM/OB should succeed', str(exc))
    bare.lines.all().delete()
    bare.delete()

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

    # --- 2b) GTKH theo đơn = NVL BOM + nhân công SMV áp dụng ---
    so_line = order.lines.select_related('bom_version').prefetch_related('routing_lines').get()
    order_costing = compute_costing_for_sales_line(so_line)
    bom_costing = compute_costing(bom)
    if order_costing.labor_cost <= 0 and not snaps:
        fail('2b.GTKH labor=0 and no snapshot')
    else:
        ok(f'2b.GTKH labor={order_costing.labor_cost} (BOM ProcessStep labor={bom_costing.labor_cost})')
    sheet = None
    try:
        sheet = build_order_sheet_from_kv(
            name=f'E2E GTKH {order.code}',
            date_from=today,
            date_to=today,
            kv_order_code=order.code,
            code=f'E2E-{order.code}'[:40],
        )
        cl = sheet.lines.get()
        unit = order_costing.total_cost.quantize(Decimal('0.01'))
        if cl.unit_cost != unit:
            fail('2b.GTKH unit_cost', f'got {cl.unit_cost} want {unit}')
        else:
            ok(f'2b.GTKH sheet {sheet.code} unit={cl.unit_cost} qty={cl.qty} total={sheet.total_cost}')
        if cl.qty != Decimal('12.00'):
            fail('2b.GTKH qty', str(cl.qty))
    except Exception as exc:
        fail('2b.GTKH build', f'{type(exc).__name__}: {exc}')

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
        snap_names = [
            (s.op_name_vi or s.op_code or '').strip()
            for s in so_line.routing_lines.order_by('seq_no', 'id')
        ]
        snap_names = [n for n in snap_names if n]
        mo_names = [s.process_name for s in steps]
        if not steps:
            fail('4c.MO has no process steps')
        elif snap_names and [n.strip().casefold() for n in mo_names] != [n.strip().casefold() for n in snap_names]:
            fail('4c.steps mismatch snapshot', f'mo={mo_names} snap={snap_names}')
        else:
            ok(f'4c.MO process steps from SMV snapshot đơn ({len(steps)})')

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
        lines=[LineInput(product_code=product_code, qty=Decimal('5'), routing_id=routing.pk)],
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

    # --- cleanup test orders/MOs / GTKH ---
    if sheet is not None:
        sheet.lines.all().delete()
        sheet.delete()
        ok('cleanup deleted E2E GTKH sheet')
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
