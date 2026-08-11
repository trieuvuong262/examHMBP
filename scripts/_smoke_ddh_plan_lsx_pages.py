"""Smoke HTTP: các màn ĐĐH → xác nhận → board kế hoạch → LSX → năng lực.

Chạy trên VPS:
  docker compose exec -T web python manage.py shell < scripts/_smoke_ddh_plan_lsx_pages.py
"""

from __future__ import annotations

import traceback

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from san_xuat.hub_models import SxMoProcessStep, SxProductionOrder, SxSalesOrder

HOST = 'portal.justplay.vn'
PASS: list[str] = []
FAIL: list[str] = []
ERROR_MARKERS = (
    'NoReverseMatch',
    'TemplateSyntaxError',
    'Exception Type:',
    'Traceback (most recent call last)',
    'Server Error (500)',
)


def ok(m: str) -> None:
    PASS.append(m)
    print('PASS:', m)


def fail(m: str, d: str = '') -> None:
    FAIL.append(m)
    print('FAIL:', m, d[:200] if d else '')


def check(client: Client, label: str, url: str, *, expect: int | tuple[int, ...] = 200, follow: bool = False) -> None:
    if isinstance(expect, int):
        expect = (expect,)
    try:
        r = client.get(url, follow=follow)
    except Exception as exc:
        fail(label, f'exception: {exc}')
        return
    code = r.status_code
    body = ''
    try:
        body = r.content.decode('utf-8', errors='replace')
    except Exception:
        body = ''
    if code == 500 or any(m in body for m in ERROR_MARKERS):
        fail(label, f'status={code} marker/500')
        return
    if code not in expect:
        fail(label, f'status={code} want {expect}')
        return
    ok(f'{label} → {code}')


def main() -> int:
    User = get_user_model()
    user = (
        User.objects.filter(is_superuser=True).order_by('id').first()
        or User.objects.filter(is_staff=True).order_by('id').first()
    )
    if not user:
        fail('no user')
        return 1
    client = Client(HTTP_HOST=HOST)
    client.force_login(user)
    print(f'user={user.username}')

    # --- Đơn hàng ---
    check(client, 'sales_order_list', reverse('san_xuat:sales_order_list'))
    check(client, 'sales_order_create', reverse('san_xuat:sales_order_create'))
    check(client, 'sales_order_confirm_list', reverse('san_xuat:sales_order_confirm_list'))

    order = (
        SxSalesOrder.objects.filter(is_demo=False)
        .order_by('-id')
        .first()
    )
    if order:
        check(client, f'sales_order_detail#{order.pk}', reverse('san_xuat:sales_order_detail', args=[order.pk]))
    else:
        print('WARN: no sales order for detail')

    # draft / confirmed samples if exist
    for st, label in (
        (SxSalesOrder.CONFIRM_DRAFT, 'draft'),
        (SxSalesOrder.CONFIRM_CONFIRMED, 'confirmed'),
    ):
        o = SxSalesOrder.objects.filter(is_demo=False, confirm_status=st).order_by('-id').first()
        if o and (not order or o.pk != order.pk):
            check(client, f'sales_order_detail_{label}#{o.pk}', reverse('san_xuat:sales_order_detail', args=[o.pk]))

    # --- Board kế hoạch (các tab / mode) ---
    board = reverse('san_xuat:plan_board')
    for qs, label in (
        ('?mode=list&tab=queue', 'board_queue'),
        ('?mode=list&tab=released', 'board_released'),
        ('', 'board_default'),
    ):
        check(client, label, board + qs)
    check(client, 'plan_route', reverse('san_xuat:plan_route'))
    check(client, 'team_work_goods', reverse('san_xuat:team_work_goods'))

    # API BOM versions (dùng modal Chuyển SX)
    product = None
    o2 = SxSalesOrder.objects.filter(is_demo=False, confirm_status=SxSalesOrder.CONFIRM_CONFIRMED).prefetch_related('lines').order_by('-id').first()
    if o2:
        ln = o2.lines.first()
        if ln:
            product = ln.product_code
    if product:
        check(client, 'mo_bom_versions_api', reverse('san_xuat:mo_bom_versions') + f'?product_code={product}')
    else:
        check(client, 'mo_bom_versions_api_empty', reverse('san_xuat:mo_bom_versions') + '?product_code=')

    # --- LSX ---
    check(client, 'dispatch_mo_list', reverse('san_xuat:dispatch_mo'))
    check(client, 'dispatch_mo_create', reverse('san_xuat:dispatch_mo_create'))
    mo = SxProductionOrder.objects.filter(is_demo=False).order_by('-id').first()
    if mo:
        check(client, f'dispatch_mo_detail#{mo.pk}', reverse('san_xuat:dispatch_mo_detail', args=[mo.pk]))
        step = SxMoProcessStep.objects.filter(production_order=mo).order_by('sequence').first()
        if step:
            check(
                client,
                f'mo_process_step#{step.pk}',
                reverse('san_xuat:dispatch_mo_process_step_detail', args=[step.pk]),
            )
    else:
        print('WARN: no MO for detail')

    # --- Năng lực ---
    check(client, 'capacity_list', reverse('san_xuat:capacity_list'))
    check(client, 'capacity_setup', reverse('san_xuat:capacity_setup'))
    check(client, 'capacity_create', reverse('san_xuat:capacity_create'))
    # redirect cũ
    check(
        client,
        'capacity_load_redirect',
        reverse('san_xuat:capacity_load_matrix'),
        expect=(302, 301),
    )

    # related plan pages (một số URL cũ redirect về board)
    for name, expect, follow in (
        ('san_xuat:plan_progress_monitor', (200, 302), True),
        ('san_xuat:plan_audit_log', (200,), False),
        ('san_xuat:plan_overall', (200, 302), True),
        ('san_xuat:plan_detail', (200, 302), True),
        ('san_xuat:plan_npl', (200,), False),
        ('san_xuat:plan_stub', (200, 302), True),
    ):
        try:
            url = reverse(name)
        except Exception:
            print(f'SKIP: {name} not routed')
            continue
        check(client, name.split(':')[-1], url, expect=expect, follow=follow)

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
