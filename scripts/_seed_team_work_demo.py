"""Seed demo Công việc tổ — LSX + CD mẫu + gán NV; rồi smoke 6 board + assign.

Chạy trên VPS:
  docker compose exec -T web python manage.py shell < scripts/_seed_team_work_demo.py
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from san_xuat.hub_models import (
    SxProductionOrder,
    SxProductionOrderLine,
    SxSalesOrder,
    SxSalesOrderLine,
)
from san_xuat.services.order_progress_sheet import (
    ensure_progress_work_centers,
    seed_order_plan_steps_from_template,
)
from san_xuat.services.products import resolve_product_ref, search_products
from san_xuat.services.progress_template import TEAM_SLUGS, progress_steps
from san_xuat.services.team_work import (
    assign_team_work,
    build_team_work_rows,
    ensure_mo_step_for_template,
)

DEMO_SO = 'DH-DEMO-TW-001'
DEMO_MO = 'LSX-DEMO-TW-001'
DEMO_NOTE = '[DEMO công việc tổ]'

SIZE_QTY = [
    ('S', Decimal('100')),
    ('M', Decimal('150')),
    ('L', Decimal('150')),
    ('XL', Decimal('150')),
    ('2XL', Decimal('100')),
]

# Gán mẫu: process_key → số NV lấy từ user active
ASSIGN_SAMPLES = (
    ('cat_ao', 1),
    ('cat_quan', 1),
    ('inep_la_co', 2),
    ('inep_tru', 1),
    ('theu_ao', 1),
    ('may_la_co', 2),
    ('may_rap_vai', 1),
    ('ht_ui', 1),
    ('ht_gap', 1),
    ('gh_tp', 1),
)


def _pick_product() -> tuple[str, str]:
    ref = resolve_product_ref('JP') or resolve_product_ref('SP')
    if ref:
        return ref.code, (ref.name or '').strip()
    rows = search_products('', limit=5)
    if rows:
        return rows[0]['code'], (rows[0].get('name') or '').strip()
    return 'DEMO-TEE-001', 'Áo demo Công việc tổ'


def _pick_users(n: int) -> list[int]:
    User = get_user_model()
    ids = list(
        User.objects.filter(is_active=True)
        .order_by('id')
        .values_list('id', flat=True)[: max(n, 3)]
    )
    return ids[:n] if ids else []


@transaction.atomic
def seed() -> SxProductionOrder:
    ensure_progress_work_centers()
    today = timezone.localdate()
    product_code, product_name = _pick_product()
    product_name = product_name or 'Áo demo Công việc tổ'

    SxProductionOrder.objects.filter(code=DEMO_MO).delete()
    SxSalesOrder.objects.filter(code=DEMO_SO).delete()

    total = sum((q for _, q in SIZE_QTY), Decimal('0'))
    so = SxSalesOrder.objects.create(
        code=DEMO_SO,
        customer_name='Khách demo Công việc tổ',
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

    # Đảm bảo mọi CD mẫu có bước trên LSX
    for sd in progress_steps():
        ensure_mo_step_for_template(mo=mo, step_def=sd)

    # Gán NV mẫu
    assigned = []
    for process_key, n_users in ASSIGN_SAMPLES:
        uids = _pick_users(n_users)
        if not uids:
            continue
        step = assign_team_work(
            mo_id=mo.pk,
            process_key=process_key,
            user_ids=uids,
            assigned_by=None,
        )
        assigned.append((process_key, step.pk, uids))

    print('SEED_OK')
    print('so', so.pk, so.code)
    print('mo', mo.pk, mo.code)
    print('steps', mo.mo_process_steps.count())
    print('assigned', len(assigned))
    for item in assigned:
        print('  assign', item)
    return mo


def smoke(mo: SxProductionOrder) -> None:
    print('SMOKE')
    q = DEMO_MO
    for slug, group_key, _mk, label in TEAM_SLUGS:
        team, rows = build_team_work_rows(slug=slug, search=q)
        demo_rows = [r for r in rows if r.mo.pk == mo.pk]
        with_assignee = [r for r in demo_rows if r.assignees]
        with_step = [r for r in demo_rows if r.mo_step]
        print(
            f'  {slug}/{label}: rows={len(demo_rows)} steps={len(with_step)} '
            f'assigned={len(with_assignee)} group={team["group_key"]}'
        )
        assert demo_rows, f'No rows for {slug}'
        assert all(r.mo_step for r in demo_rows), f'Missing mo_step on {slug}'

    # Re-assign một CD (đổi NV) để xác nhận API
    users = _pick_users(2)
    if users:
        step = assign_team_work(
            mo_id=mo.pk,
            process_key='inep_la_co',
            user_ids=users,
            assigned_by=None,
        )
        print('reassign_inep_la_co', step.pk, users)
        _, rows = build_team_work_rows(slug='inep', search=q)
        hit = next(
            (r for r in rows if r.mo.pk == mo.pk and r.step_def.key == 'inep_la_co'),
            None,
        )
        assert hit is not None
        got = {a['id'] for a in hit.assignees}
        assert got == set(users), (got, users)
        print('reassign_ok', sorted(got))

    print('SMOKE_OK')
    print('urls')
    for slug, _gk, _mk, label in TEAM_SLUGS:
        print(f'  {label}: /san-xuat/cong-viec-to/{slug}/?q={DEMO_MO}')
    print(f'  mo: /san-xuat/dieu-phoi/lenh-sx/{mo.pk}/')


mo = seed()
smoke(mo)
