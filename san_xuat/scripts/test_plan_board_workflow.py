"""Workflow test: DDH confirm -> plan board -> rank -> release LSX."""
from __future__ import annotations
import traceback
from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from san_xuat.hub_models import SxSalesOrder
from san_xuat.services.plan_board import (
    build_plan_board_rows, pipeline_counts, recompute_plan_ranks,
    release_order_to_production, set_plan_priority,
)
from san_xuat.services.sales_orders import LineInput, confirm_sales_order, create_sales_order
results = []
def log(step, ok, detail=''):
    results.append((step, ok, detail))
    print(('OK' if ok else 'FAIL'), step, '-', detail)
def pick_product_code():
    from san_xuat.models import ProductTechDoc
    from san_xuat.services.bom import get_working_bom
    for doc in ProductTechDoc.objects.order_by('-id')[:40]:
        if get_working_bom(doc):
            return doc.product_code
    raise RuntimeError('No product with working BOM')
def run():
    User = get_user_model()
    user = User.objects.filter(is_superuser=True).order_by('id').first() or User.objects.order_by('id').first()
    today = timezone.localdate()
    product_code = pick_product_code()
    log('pick_product', True, product_code)
    order = create_sales_order(code='', customer_name='[TEST-PLAN-BOARD]', request_date=today, due_date=today + timedelta(days=7), notes='workflow auto test', lines=[LineInput(product_code=product_code, product_name='', qty=Decimal('5'), qty_scrap_rate=Decimal('0'))], user=user)
    log('create_order', True, order.code)
    order = confirm_sales_order(order_id=order.pk)
    log('confirm_enqueue', order.confirm_status == 'confirmed' and order.plan_status == 'queued' and bool(order.plan_queued_at), f'status={order.plan_status}')
    set_plan_priority(order_id=order.pk, priority=SxSalesOrder.PRIORITY_HIGH)
    n = recompute_plan_ranks()
    order.refresh_from_db()
    log('rank', order.plan_status == 'ranked' and order.plan_rank is not None, f'rank={order.plan_rank} score={order.plan_score} n={n}')
    rows = build_plan_board_rows()
    log('board_rows', any(r.order.pk == order.pk for r in rows), f'queue={len(rows)}')
    counts = pipeline_counts()
    log('pipeline_counts', counts.get('waiting', 0) >= 1, str(counts))
    created = release_order_to_production(order_id=order.pk, user=user)
    order.refresh_from_db()
    log('release_mo', len(created) >= 1 and order.plan_status == 'released' and all(m.sales_order_id == order.pk for m in created), f'mos={[m.code for m in created]} status={order.plan_status}')
    client = Client(HTTP_HOST='testserver')
    client.force_login(user)
    r_board = client.get(reverse('san_xuat:plan_board'))
    log('http_plan_board', r_board.status_code == 200, str(r_board.status_code))
    for name in ('plan_overall', 'plan_detail', 'plan_progress_monitor', 'plan_stub'):
        resp = client.get(reverse(f'san_xuat:{name}'))
        log(f'redirect_{name}', resp.status_code in (301, 302) and '/ke-hoach/bang' in (resp.url or ''), f'{resp.status_code} -> {resp.url}')
    r_released = client.get(reverse('san_xuat:plan_board') + '?tab=released')
    body = r_released.content.decode('utf-8', errors='ignore')
    log('http_released_shows_order', r_released.status_code == 200 and order.code in body, str(r_released.status_code))
    failed = [r for r in results if not r[1]]
    print('---')
    print(f'PASS {len(results)-len(failed)}/{len(results)}')
    if failed:
        print('FAILED:', ', '.join(f[0] for f in failed))
        raise SystemExit(1)
try:
    run()
except Exception:
    traceback.print_exc()
    raise SystemExit(1)
