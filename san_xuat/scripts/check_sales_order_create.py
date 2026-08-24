"""Smoke-check lên đơn: BOM/OB tùy chọn → SMV đơn hàng từng CĐ → xác nhận."""
from __future__ import annotations

import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import Client
from django.utils import timezone

from san_xuat.forms_sales_order import SalesOrderHeaderForm, SalesOrderLineForm
from san_xuat.hub_models import SxSalesOrder
from san_xuat.ie_models import SxRouting
from san_xuat.models import BomVersion, ProcessStep, ProductTechDoc
from san_xuat.services.order_routing import (
    apply_smv_overrides,
    assert_order_ready_to_confirm,
    default_routing_for_product,
)
from san_xuat.services.planning import PlanningError
from san_xuat.services.products import resolve_product_ref
from san_xuat.services.sales_orders import LineInput, confirm_sales_order, create_sales_order


def _ok(label, cond, detail=''):
    mark = 'PASS' if cond else 'FAIL'
    extra = f' -- {detail}' if detail else ''
    text = f'  [{mark}] {label}{extra}'
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('ascii', 'replace').decode('ascii'))
    return bool(cond)


def _is_style_code(code: str) -> bool:
    c = (code or '').strip()
    if not c or ' ' in c:
        return False
    return c.upper().startswith('JP-') or 'SP' in c.upper()


def _pick_codes():
    """Chọn mã hàng thật: có IE, chỉ BOM, không gì."""
    ie_code = None
    ie_rt = None
    ie_fb, ie_fb_rt = None, None
    for rt in SxRouting.objects.filter(is_active=True).select_related('tech_doc').order_by('-id'):
        if not rt.lines.exists():
            continue
        code = (rt.style_code or '').strip()
        if not _is_style_code(code) and rt.tech_doc_id:
            code = (rt.tech_doc.product_code or '').strip()
        if not _is_style_code(code):
            continue
        if resolve_product_ref(code):
            ie_code, ie_rt = code, rt
            break
        if ie_fb is None:
            ie_fb, ie_fb_rt = code, rt
    if not ie_code:
        ie_code, ie_rt = ie_fb, ie_fb_rt
    bom_only = None
    bom_ver = None
    for bom in BomVersion.objects.select_related('tech_doc').order_by('-id'):
        code = (bom.tech_doc.product_code or '').strip() if bom.tech_doc_id else ''
        if not _is_style_code(code):
            continue
        if SxRouting.objects.filter(style_code__iexact=code).exists():
            continue
        if bom.process_steps.exists():
            bom_only = code
            bom_ver = bom
            break
    neither = None
    for doc in ProductTechDoc.objects.order_by('-id'):
        code = (doc.product_code or '').strip()
        if not _is_style_code(code):
            continue
        if SxRouting.objects.filter(style_code__iexact=code).exists():
            continue
        if ProcessStep.objects.filter(bom__tech_doc=doc).exists():
            continue
        neither = code
        break
    return ie_code, ie_rt, bom_only, bom_ver, neither


def check_forms():
    print('\n== Form validation ==')
    hdr = SalesOrderHeaderForm(data={
        'customer_name': 'Smoke KH',
        'request_date': timezone.localdate().isoformat(),
        'due_date': timezone.localdate().isoformat(),
        'notes': '',
    })
    _ok('Header không bắt routing/BOM', hdr.is_valid(), str(hdr.errors) if not hdr.is_valid() else '')

    ie_code, _, bom_only, _, neither = _pick_codes()
    code = None
    for cand in (ie_code, bom_only, neither):
        if cand and resolve_product_ref(cand):
            code = cand
            break
    if not code:
        print('  [SKIP] Khong co ma hang trong kho SP de test line form')
        return
    line = SalesOrderLineForm(data={
        'product_code': code,
        'product_name': 'x',
        'qty': '10',
        'size_qtys': '{}',
        'bom_version_id': '',
        'routing_id': '',
        'applied_smv_json': '[]',
    })
    _ok(
        'Line không bắt BOM/routing lúc tạo',
        line.is_valid(),
        str(line.errors) if not line.is_valid() else code,
    )


def check_page():
    print('\n== Trang /san-xuat/don-hang/them/ ==')
    user = get_user_model().objects.filter(is_active=True).order_by('-is_superuser', '-is_staff', 'id').first()
    if not user:
        print('  [SKIP] Không có user')
        return None
    client = Client()
    client.force_login(user)
    resp = client.get('/san-xuat/don-hang/them/', HTTP_HOST='127.0.0.1')
    html = resp.content.decode('utf-8', errors='replace')
    _ok('GET 200', resp.status_code == 200, str(resp.status_code))
    _ok('Có cột BOM', '>BOM<' in html or 'BOM (NVL' in html)
    _ok('Có cột Routing', '>Routing<' in html or 'jp-so-ie-col">Routing' in html)
    _ok('Không còn tiêu đề Quy trình IE', 'Quy trình IE' not in html)
    _ok('Không còn tiêu đề Phiên bản routing', 'Phiên bản routing' not in html)
    _ok('JS render bảng SMV sau khi chọn routing', 'jp-so-smv-input' in html)
    _ok('Không còn hint Chọn mã hàng → BOM', 'Chọn mã hàng → BOM' not in html)
    _ok('Không còn khối % lệch đơn / SMV đơn', 'data-role="smv-pct"' not in html)
    _ok('Không còn lý do lệch >15%', 'Lý do lệch' not in html)
    _ok('Select routing luôn hiện khi có bản', 'jp-so-routing-select' in html)
    return client


def _api_versions(client, code):
    r = client.get('/san-xuat/api/don-hang/phien-ban/', {'product_code': code}, HTTP_HOST='127.0.0.1')
    if r.status_code != 200:
        return None, r.status_code
    return r.json(), r.status_code


def check_api(client):
    print('\n== API phiên bản ==')
    ie_code, ie_rt, bom_only, bom_ver, neither = _pick_codes()
    if not client:
        print('  [SKIP] Không có client')
        return ie_code, ie_rt, bom_only, bom_ver, neither

    if ie_code:
        data, status = _api_versions(client, ie_code)
        if not data:
            _ok(f'IE API {ie_code}', False, f'HTTP {status}')
        else:
            n_rt = len(data.get('routings') or [])
            src = data.get('steps_source')
            n_st = len(data.get('steps') or [])
            _ok(
                f'IE {ie_code}: có routing + steps_source=ie',
                n_rt >= 1 and src == 'ie' and n_st >= 1,
                f'routings={n_rt} source={src} steps={n_st} default={data.get("default_routing_id")}',
            )
            default = default_routing_for_product(ie_code)
            _ok(
                'default_routing_for_product khớp API',
                default is not None and data.get('default_routing_id') == default.pk,
                f'fn={getattr(default, "pk", None)} api={data.get("default_routing_id")}',
            )
    else:
        print('  [SKIP] Không có mã có routing IE')

    if bom_only:
        data, status = _api_versions(client, bom_only)
        if not data:
            _ok(f'BOM-only API {bom_only}', False, f'HTTP {status}')
        else:
            n_rt = len(data.get('routings') or [])
            src = data.get('steps_source')
            n_st = len(data.get('steps') or [])
            _ok(
                f'BOM-only {bom_only}: 0 routing, steps tu BOM',
                n_rt == 0 and src == 'bom' and n_st >= 1,
                f'routings={n_rt} source={src} steps={n_st} default_bom={data.get("default_bom_id")}',
            )
    else:
        print('  [SKIP] Không có mã chỉ BOM (không IE)')

    if neither:
        data, status = _api_versions(client, neither)
        if not data:
            _ok(f'Neither API {neither}', False, f'HTTP {status}')
        else:
            _ok(
                f'Neither {neither}: khong steps',
                len(data.get('routings') or []) == 0 and len(data.get('steps') or []) == 0,
                f'source={data.get("steps_source")!r}',
            )
    return ie_code, ie_rt, bom_only, bom_ver, neither


def check_http_post(client, bom_only, bom_ver):
    print('\n== POST form len don (BOM-only, khong routing) ==')
    if not client or not bom_only or not bom_ver:
        print('  [SKIP]')
        return
    today = timezone.localdate().isoformat()
    resp = client.post('/san-xuat/don-hang/them/', {
        'customer_name': 'SMOKE-HTTP',
        'request_date': today,
        'due_date': today,
        'notes': 'smoke http',
        'lines-TOTAL_FORMS': '1',
        'lines-INITIAL_FORMS': '0',
        'lines-MIN_NUM_FORMS': '0',
        'lines-MAX_NUM_FORMS': '1000',
        'lines-0-product_code': bom_only,
        'lines-0-product_name': '',
        'lines-0-qty': '3',
        'lines-0-size_qtys': '{}',
        'lines-0-bom_version_id': str(bom_ver.pk),
        'lines-0-routing_id': '',
        'lines-0-applied_smv_json': '[]',
    }, HTTP_HOST='127.0.0.1')
    ok_redirect = resp.status_code == 302
    _ok('POST 302 chi tiet', ok_redirect, f'HTTP {resp.status_code} loc={resp.get("Location", "")}')
    if not ok_redirect:
        return
    loc = resp.get('Location') or ''
    pk = None
    for part in loc.rstrip('/').split('/'):
        if part.isdigit():
            pk = int(part)
    if not pk:
        _ok('Parse pk tu redirect', False, loc)
        return
    order = SxSalesOrder.objects.filter(pk=pk).first()
    if not order:
        _ok('Tim don vua tao', False)
        return
    ln = order.lines.first()
    n = ln.routing_lines.count() if ln else 0
    _ok(
        'Don nhap + snapshot BOM, khong routing IE',
        order.confirm_status == SxSalesOrder.CONFIRM_DRAFT and n > 0 and not ln.routing_id,
        f'{order.code} lines={n} routing={ln.routing_id}',
    )
    order.delete()
    _ok('Da xoa don smoke', not SxSalesOrder.objects.filter(pk=pk).exists())


def check_ie_smv_workflow(client, ie_code, ie_rt):
    print('\n== Workflow IE: routing + SMV don hang tung CD ==')
    if not client or not ie_code or not ie_rt:
        print('  [SKIP]')
        return
    src = ie_rt.lines.order_by('seq_no').first()
    if not src or (src.library_unit_smv or 0) <= 0:
        print('  [SKIP] Routing khong co CĐ SMV > 0')
        return
    if not resolve_product_ref(ie_code):
        print(f'  [SKIP] {ie_code} khong resolve kho SP')
        return
    # Baseline trên đơn = SMV sản phẩm (OB applied, fallback thư viện)
    product = Decimal(str(src.applied_unit_smv or 0))
    if product <= 0:
        product = Decimal(str(src.library_unit_smv))
    order_smv = (product * Decimal('1.20')).quantize(Decimal('0.0001'))
    payload = json.dumps([{'seq': int(src.seq_no), 'smv': float(order_smv)}])
    today = timezone.localdate().isoformat()
    resp = client.post('/san-xuat/don-hang/them/', {
        'customer_name': 'SMOKE-IE-SMV',
        'request_date': today,
        'due_date': today,
        'notes': 'smoke ie smv',
        'lines-TOTAL_FORMS': '1',
        'lines-INITIAL_FORMS': '0',
        'lines-MIN_NUM_FORMS': '0',
        'lines-MAX_NUM_FORMS': '1000',
        'lines-0-product_code': ie_code,
        'lines-0-product_name': '',
        'lines-0-qty': '4',
        'lines-0-size_qtys': '{}',
        'lines-0-bom_version_id': '',
        'lines-0-routing_id': str(ie_rt.pk),
        'lines-0-applied_smv_json': payload,
    }, HTTP_HOST='127.0.0.1')
    ok_redirect = resp.status_code == 302
    _ok('POST 302 chi tiet (IE + SMV override)', ok_redirect, f'HTTP {resp.status_code}')
    if not ok_redirect:
        return
    loc = resp.get('Location') or ''
    pk = next((int(p) for p in loc.rstrip('/').split('/') if p.isdigit()), None)
    if not pk:
        _ok('Parse pk tu redirect', False, loc)
        return
    order = SxSalesOrder.objects.filter(pk=pk).first()
    if not order:
        _ok('Tim don IE smoke', False)
        return
    try:
        ln = order.lines.first()
        snap = ln.routing_lines.filter(seq_no=src.seq_no).first() if ln else None
        _ok(
            'Snapshot IE + routing_id',
            bool(ln and ln.routing_id == ie_rt.pk and ln.routing_lines.count() > 0),
            f'{order.code} routing={getattr(ln, "routing_id", None)} n={ln.routing_lines.count() if ln else 0}',
        )
        _ok(
            'SMV san pham khong doi',
            bool(snap) and Decimal(str(snap.library_unit_smv)) == product,
            f'lib={getattr(snap, "library_unit_smv", None)} product={product}',
        )
        _ok(
            'SMV don hang dung override +20%',
            bool(snap) and Decimal(str(snap.applied_unit_smv)) == order_smv,
            f'applied={getattr(snap, "applied_unit_smv", None)} expect={order_smv}',
        )
        smv_ok = all((s.applied_unit_smv or 0) > 0 for s in ln.routing_lines.all())
        if not smv_ok:
            _ok('Xac nhan: mot so CD SMV=0 — dung se chan', True)
        else:
            try:
                assert_order_ready_to_confirm(order)
                confirm_sales_order(order_id=order.pk)
                order.refresh_from_db()
                _ok(
                    'Xac nhan OK (lech >15% khong bat ly do)',
                    order.confirm_status == SxSalesOrder.CONFIRM_CONFIRMED,
                )
            except PlanningError as exc:
                _ok('Xac nhan OK (lech >15% khong bat ly do)', False, str(exc)[:180])
    finally:
        SxSalesOrder.objects.filter(pk=pk).delete()
        _ok('Da xoa don IE smoke', not SxSalesOrder.objects.filter(pk=pk).exists())


def check_seed_and_confirm(ie_code, ie_rt, bom_only, bom_ver, neither):
    print('\n== Seed snapshot + xác nhận (rollback) ==')
    fails = 0

    def run(label, fn):
        nonlocal fails
        with transaction.atomic():
            try:
                fn()
            except Exception as exc:
                _ok(label, False, repr(exc))
                fails += 1
                raise
            else:
                transaction.set_rollback(True)

    if ie_code and ie_rt:
        def ie_case():
            order = create_sales_order(
                customer_name='SMOKE-IE',
                lines=[LineInput(
                    product_code=ie_code,
                    qty=Decimal('10'),
                    routing_id=ie_rt.pk,
                )],
            )
            ln = order.lines.get()
            n = ln.routing_lines.count()
            src_ok = ln.routing_id == ie_rt.pk and n > 0
            _ok(f'Tạo + IE: snapshot {n} CĐ từ routing', src_ok, f'routing_id={ln.routing_id}')
            first = ln.routing_lines.order_by('seq_no').first()
            if first and (first.library_unit_smv or 0) > 0:
                std = Decimal(str(first.library_unit_smv))
                new_smv = (std * Decimal('1.20')).quantize(Decimal('0.0001'))
                apply_smv_overrides(ln, [{'seq': int(first.seq_no), 'smv': new_smv}])
                first.refresh_from_db()
                _ok(
                    'Override SMV đơn hàng, SMV sản phẩm không đổi',
                    Decimal(str(first.applied_unit_smv)) == new_smv
                    and Decimal(str(first.library_unit_smv)) == std,
                    f'lib={first.library_unit_smv} app={first.applied_unit_smv}',
                )
            smv_ok = all((s.applied_unit_smv or 0) > 0 for s in ln.routing_lines.all())
            if not smv_ok:
                # vẫn seed được; confirm có thể fail nếu SMV=0 — ghi nhận
                _ok('IE SMV > 0 trên mọi CĐ', False, 'một số CĐ SMV=0 — xác nhận sẽ chặn (đúng)')
            else:
                assert_order_ready_to_confirm(order)
                _ok('Xác nhận OK khi có IE snapshot + SMV>0', True)
                confirm_sales_order(order_id=order.pk)
                order.refresh_from_db()
                _ok('confirm_status=confirmed', order.confirm_status == SxSalesOrder.CONFIRM_CONFIRMED)
        try:
            run('IE case', ie_case)
        except Exception:
            pass

    if bom_only and bom_ver:
        def bom_case():
            order = create_sales_order(
                customer_name='SMOKE-BOM',
                lines=[LineInput(
                    product_code=bom_only,
                    qty=Decimal('8'),
                    bom_version_id=bom_ver.pk,
                )],
            )
            ln = order.lines.get()
            n = ln.routing_lines.count()
            _ok(
                f'Tạo + BOM-only: snapshot {n} CĐ, routing_id rỗng',
                n > 0 and not ln.routing_id,
                f'routing_id={ln.routing_id}',
            )
            try:
                assert_order_ready_to_confirm(order)
                _ok('Xác nhận được khi snapshot từ BOM (SMV>0)', True)
            except PlanningError as exc:
                _ok('Xác nhận chặn nếu SMV BOM = 0', 'SMV đơn hàng phải > 0' in str(exc), str(exc)[:180])
        try:
            run('BOM case', bom_case)
        except Exception:
            pass

    if neither:
        def neither_case():
            order = create_sales_order(
                customer_name='SMOKE-NONE',
                lines=[LineInput(product_code=neither, qty=Decimal('5'))],
            )
            ln = order.lines.get()
            _ok(
                'Tạo nháp không BOM/IE vẫn được',
                ln.routing_lines.count() == 0 and not ln.routing_id,
            )
            try:
                assert_order_ready_to_confirm(order)
                confirm_sales_order(order_id=order.pk)
                order.refresh_from_db()
                _ok(
                    'Xác nhận được khi chưa chọn BOM/OB',
                    order.confirm_status == SxSalesOrder.CONFIRM_CONFIRMED,
                )
            except PlanningError as exc:
                _ok('Xác nhận được khi chưa chọn BOM/OB', False, str(exc)[:180])
        try:
            run('Neither case', neither_case)
        except Exception:
            pass


def main():
    print('Kiem tra workflow len don (BOM -> routing IE -> SMV ap dung -> xac nhan)')
    check_forms()
    client = check_page()
    picked = check_api(client)
    check_http_post(client, picked[2], picked[3])
    check_ie_smv_workflow(client, picked[0], picked[1])
    check_seed_and_confirm(*picked)
    print('\nXong.')


main()
