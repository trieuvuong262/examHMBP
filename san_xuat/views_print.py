"""Màn in phiếu A5 — P0 + P1 chứng từ sản xuất."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone

from assessment.decorators import module_perm_required
from hrm.menu_permissions import handle_menu_access_denied, user_can_print_menu
from hrm.module_permissions import MODULE_SAN_XUAT
from san_xuat.hub_models import (
    SxFgReceiptRequest,
    SxMaterialIssueRequest,
    SxNcrCase,
    SxNplPurchaseRequest,
    SxPackingRecord,
    SxProductionOrder,
    SxPurchaseOrder,
    SxQcAlert,
    SxQcInspection,
    SxSubcontractOrder,
    SxWipHandover,
)
from san_xuat.print_company import (
    COMPANY_ADDRESS,
    COMPANY_NAME,
    COMPANY_TAX_CODE,
    SIGNATURES,
)


def _person_name(user) -> str:
    if not getattr(user, 'pk', None):
        return ''
    profile = getattr(user, 'profile', None)
    name = (getattr(profile, 'full_name', '') or '').strip()
    return name or (user.get_full_name() or '').strip() or user.get_username()


def _print_base_ctx(*, print_title: str, back_url: str, signature_key: str, doc_date, request, doc_code: str = ''):
    return {
        'print_title': print_title,
        'back_url': back_url,
        'company_name': COMPANY_NAME,
        'company_tax_code': COMPANY_TAX_CODE,
        'company_address': COMPANY_ADDRESS,
        'signature_roles': SIGNATURES[signature_key],
        'doc_code': doc_code,
        'doc_date': doc_date,
        'printed_at': timezone.localtime(),
        'autoprint': (request.GET.get('autoprint') or '') in ('1', 'true', 'yes'),
    }


def _bom_lines_for_mo(mo: SxProductionOrder) -> list[dict]:
    from san_xuat.services.bom_need import explode_for_mo, needs_as_display_dicts

    return needs_as_display_dicts(explode_for_mo(mo))


@module_perm_required(MODULE_SAN_XUAT, 'print')
def print_mo(request, pk: int):
    mo = get_object_or_404(
        SxProductionOrder.objects.select_related('bom_version', 'sales_order').prefetch_related(
            'bom_version__lines__material',
            'sales_order__lines',
            'lines',
        ),
        pk=pk,
    )
    return render(request, 'san_xuat/print/mo_a5.html', {
        **_print_base_ctx(
            print_title=f'In lệnh sản xuất {mo.code}',
            back_url=reverse('san_xuat:dispatch_mo_detail', args=[mo.pk]),
            signature_key='mo',
            doc_code=mo.code,
            doc_date=mo.order_date or timezone.localdate(),
            request=request,
        ),
        'mo': mo,
        'bom_lines': _bom_lines_for_mo(mo),
    })


@module_perm_required(MODULE_SAN_XUAT, 'print')
def print_ycx(request, pk: int):
    req = get_object_or_404(
        SxMaterialIssueRequest.objects.select_related(
            'production_order',
            'stock_issue',
        ).prefetch_related('lines__preferred_location'),
        pk=pk,
    )
    mo = req.production_order
    return render(request, 'san_xuat/print/ycx_a5.html', {
        **_print_base_ctx(
            print_title=f'In yêu cầu xuất {req.code}',
            back_url=reverse('san_xuat:dispatch_material_issue_req_detail', args=[req.pk]),
            signature_key='ycx',
            doc_code=req.code,
            doc_date=req.request_date or timezone.localdate(),
            request=request,
        ),
        'req': req,
        'mo': mo,
        'lines': list(req.lines.all()),
    })


@module_perm_required(MODULE_SAN_XUAT, 'print')
def print_qc(request, pk: int):
    inspection = get_object_or_404(
        SxQcInspection.objects.select_related(
            'qc_request__production_order',
            'standard_set',
        ).prefetch_related(
            'criteria_lines__criteria',
            'defect_lines__defect__group',
            'team_results',
        ),
        pk=pk,
    )
    qc_request = inspection.qc_request
    mo = qc_request.production_order if qc_request else None
    from san_xuat.services.qc import inspection_size_plan, load_size_qtys, merge_size_rows

    saved_sizes = []
    by_size: dict = {}
    for rec in inspection.team_results.all():
        for row in load_size_qtys(rec.size_qtys):
            hit = by_size.setdefault(row['size'], {'size': row['size'], 'qty_pass': 0, 'qty_fail': 0})
            hit['qty_pass'] += row['qty_pass']
            hit['qty_fail'] += row['qty_fail']
    saved_sizes = list(by_size.values()) or list(inspection.size_qtys or [])
    return render(request, 'san_xuat/print/qc_a5.html', {
        **_print_base_ctx(
            print_title=f'In phiếu kiểm tra {inspection.code}',
            back_url=reverse('san_xuat:qc_sheet_detail', args=[inspection.pk]),
            signature_key='qc',
            doc_code=inspection.code,
            doc_date=inspection.inspected_at or timezone.localdate(),
            request=request,
        ),
        'inspection': inspection,
        'qc_request': qc_request,
        'mo': mo,
        'criteria_lines': list(inspection.criteria_lines.all()),
        'defect_lines': list(inspection.defect_lines.all()),
        'size_rows': merge_size_rows(
            inspection_size_plan(mo),
            saved_sizes,
            fallback_pass=inspection.qty_pass,
            fallback_fail=inspection.qty_fail,
        ),
    })


@module_perm_required(MODULE_SAN_XUAT, 'print')
def print_packing(request, pk: int):
    item = get_object_or_404(
        SxPackingRecord.objects.select_related(
            'production_order',
            'fg_receipt',
        ).prefetch_related('lines'),
        pk=pk,
    )
    mo = item.production_order
    return render(request, 'san_xuat/print/packing_a5.html', {
        **_print_base_ctx(
            print_title=f'In đóng gói {item.code}',
            back_url=reverse('san_xuat:packing_detail', args=[item.pk]),
            signature_key='packing',
            doc_code=item.code,
            doc_date=item.pack_date or timezone.localdate(),
            request=request,
        ),
        'item': item,
        'mo': mo,
        'lines': list(item.lines.all()),
    })


@module_perm_required(MODULE_SAN_XUAT, 'print')
def print_ycntp(request, pk: int):
    fg_req = get_object_or_404(
        SxFgReceiptRequest.objects.select_related(
            'production_order',
            'production_stat',
        ),
        pk=pk,
    )
    mo = fg_req.production_order
    return render(request, 'san_xuat/print/ycntp_a5.html', {
        **_print_base_ctx(
            print_title=f'In yêu cầu nhập thành phẩm {fg_req.code}',
            back_url=reverse('san_xuat:dispatch_fg_receipt_req_detail', args=[fg_req.pk]),
            signature_key='ycntp',
            doc_code=fg_req.code,
            doc_date=fg_req.request_date or timezone.localdate(),
            request=request,
        ),
        'fg_req': fg_req,
        'mo': mo,
    })


@module_perm_required(MODULE_SAN_XUAT, 'print')
def print_handover(request, pk: int):
    handover = get_object_or_404(
        SxWipHandover.objects.select_related('production_order'),
        pk=pk,
    )
    mo = handover.production_order
    return render(request, 'san_xuat/print/handover_a5.html', {
        **_print_base_ctx(
            print_title=f'In bàn giao {handover.code}',
            back_url=reverse('san_xuat:dispatch_wip_handover_detail', args=[handover.pk]),
            signature_key='handover',
            doc_code=handover.code,
            doc_date=handover.handover_date or timezone.localdate(),
            request=request,
        ),
        'handover': handover,
        'mo': mo,
    })


@login_required
def print_subcontract(request, pk: int):
    if not (
        user_can_print_menu(request.user, MODULE_SAN_XUAT, 'plan_board')
        or user_can_print_menu(request.user, MODULE_SAN_XUAT, 'subcontract')
    ):
        return handle_menu_access_denied(request, MODULE_SAN_XUAT, 'plan_board')
    item = get_object_or_404(
        SxSubcontractOrder.objects.select_related('production_order', 'sales_order').prefetch_related(
            'material_lines',
        ),
        pk=pk,
    )
    return render(request, 'san_xuat/print/subcontract_a5.html', {
        **_print_base_ctx(
            print_title=f'In thuê gia công {item.code}',
            back_url=reverse('san_xuat:subcontract_detail', args=[item.pk]),
            signature_key='subcontract',
            doc_code=item.code,
            doc_date=item.order_date or timezone.localdate(),
            request=request,
        ),
        'item': item,
        'mo': item.production_order,
        'material_lines': list(item.material_lines.all()),
    })


@module_perm_required(MODULE_SAN_XUAT, 'print')
def print_ncr(request, pk: int):
    case = get_object_or_404(
        SxNcrCase.objects.select_related(
            'production_order',
            'alert',
            'remake_order',
            'rework_stat',
        ),
        pk=pk,
    )
    return render(request, 'san_xuat/print/ncr_a5.html', {
        **_print_base_ctx(
            print_title=f'In không phù hợp {case.code}',
            back_url=reverse('san_xuat:ncr_detail', args=[case.pk]),
            signature_key='ncr',
            doc_code=case.code,
            doc_date=(case.confirmed_at.date() if case.confirmed_at else None)
            or (case.created_at.date() if case.created_at else timezone.localdate()),
            request=request,
        ),
        'case': case,
        'mo': case.production_order,
    })


@module_perm_required(MODULE_SAN_XUAT, 'print')
def print_qc_alert(request, pk: int):
    alert = get_object_or_404(
        SxQcAlert.objects.select_related(
            'production_order',
            'production_stat',
            'qc_request',
            'qc_inspection',
        ),
        pk=pk,
    )
    return render(request, 'san_xuat/print/qc_alert_a5.html', {
        **_print_base_ctx(
            print_title=f'In cảnh báo {alert.code}',
            back_url=reverse('san_xuat:qc_alert_detail', args=[alert.pk]),
            signature_key='qc_alert',
            doc_code=alert.code,
            doc_date=(alert.created_at.date() if alert.created_at else timezone.localdate()),
            request=request,
        ),
        'alert': alert,
        'mo': alert.production_order,
    })


@module_perm_required(MODULE_SAN_XUAT, 'print')
def print_po(request, pk: int):
    from kho_npl.models import Material

    po = get_object_or_404(
        SxPurchaseOrder.objects.select_related(
            'supplier', 'purchase_request', 'purchase_request__sales_order',
        ).prefetch_related('lines'),
        pk=pk,
    )
    order_code = ''
    if po.purchase_request_id and po.purchase_request and po.purchase_request.sales_order_id:
        order_code = po.purchase_request.sales_order.code or ''
    codes = [ln.material_code for ln in po.lines.all()]
    materials = {
        m.code.casefold(): m
        for m in Material.objects.filter(code__in=codes).select_related('color', 'specification', 'unit')
    }
    rows = []
    total_qty = 0
    total_amount = 0
    for ln in po.lines.all():
        mat = materials.get((ln.material_code or '').strip().casefold())
        spec = []
        image_url = ''
        unit = ''
        if mat:
            if mat.specification_id:
                spec.append(mat.specification.name)
            if mat.color_id:
                spec.append(mat.color.name)
            unit = mat.unit.name if mat.unit_id else ''
            if mat.image:
                try:
                    image_url = request.build_absolute_uri(mat.image.url)
                except (ValueError, OSError):
                    image_url = ''
        amount = ln.amount
        total_qty += ln.qty_ordered or 0
        total_amount += amount
        rows.append({
            'name': ln.material_name or (mat.name if mat else ln.material_code),
            'image_url': image_url,
            'spec': ' / '.join(spec),
            'unit': unit,
            'qty': ln.qty_ordered,
            'price': ln.unit_price,
            'amount': amount,
            'note': '' if order_code and (ln.notes or '').strip() == order_code else (ln.notes or ''),
        })
    pay = dict(po._meta.get_field('payment_method').choices).get(po.payment_method, '')
    supplier = po.supplier
    po_notes = po.notes or ''
    if order_code and po_notes.strip() == order_code:
        po_notes = ''
    return render(request, 'san_xuat/print/po_a4.html', {
        **_print_base_ctx(
            print_title=f'Đơn đặt hàng {po.code}',
            back_url=reverse('san_xuat:purchase_order_detail', args=[po.pk]),
            signature_key='po',
            doc_code=po.code,
            doc_date=po.order_date or (po.created_at.date() if po.created_at else timezone.localdate()),
            request=request,
        ),
        'po': po,
        'rows': rows,
        'total_qty': total_qty,
        'total_amount': total_amount,
        'payment_label': pay,
        'supplier_name': (supplier.name if supplier else '') or po.supplier_name,
        'supplier_contact': (
            ' — '.join(bit for bit in [
                (supplier.contact_name if supplier else ''),
                (supplier.phone if supplier else ''),
            ] if bit)
        ),
        'supplier_address': supplier.address if supplier else '',
        'supplier_tax': supplier.tax_code if supplier else '',
        'sheets': [{
            'supplier_name': (supplier.name if supplier else '') or po.supplier_name,
            'supplier_contact': (
                ' — '.join(bit for bit in [
                    (supplier.contact_name if supplier else ''),
                    (supplier.phone if supplier else ''),
                ] if bit)
            ),
            'supplier_address': supplier.address if supplier else '',
            'supplier_tax': supplier.tax_code if supplier else '',
            'doc_code': po.code,
            'doc_date': po.order_date or (po.created_at.date() if po.created_at else timezone.localdate()),
            'rows': rows,
            'total_qty': total_qty,
            'total_amount': total_amount,
            'payment_label': pay,
            'expected_date': po.expected_date,
            'notes': po_notes,
            'order_code': order_code,
            'preparer_name': _person_name(po.created_by),
        }],
    })


@module_perm_required(MODULE_SAN_XUAT, 'print')
def print_npl_pr(request, pk: int):
    """In A5 ngang đơn đặt hàng theo mẫu Excel, một trang mỗi nhà cung cấp."""
    from collections import defaultdict
    from decimal import Decimal

    from kho_npl.models import Material

    pr = get_object_or_404(
        SxNplPurchaseRequest.objects.select_related('created_by', 'sales_order').prefetch_related('lines__supplier'),
        pk=pk,
        is_demo=False,
    )
    lines = list(pr.lines.all())
    materials = {
        m.code.casefold(): m
        for m in Material.objects.filter(
            code__in=[ln.material_code for ln in lines],
        ).select_related('color', 'specification', 'unit')
    }
    pay_labels = dict(SxNplPurchaseRequest.PAYMENT_CHOICES)
    grouped: dict[int, list] = defaultdict(list)
    for ln in lines:
        grouped[ln.supplier_id or 0].append(ln)
    if not grouped:
        grouped[0] = []

    sheets = []
    for bucket in grouped.values():
        supplier = bucket[0].supplier if bucket and bucket[0].supplier_id else None
        rows = []
        total_qty = Decimal('0')
        total_amount = Decimal('0')
        expected = None
        pay_key = ''
        for ln in bucket:
            mat = materials.get((ln.material_code or '').strip().casefold())
            spec = []
            image_url = ''
            unit = ''
            if mat:
                if mat.specification_id:
                    spec.append(mat.specification.name)
                if mat.color_id:
                    spec.append(mat.color.name)
                unit = mat.unit.name if mat.unit_id else ''
                if mat.image:
                    try:
                        image_url = request.build_absolute_uri(mat.image.url)
                    except (ValueError, OSError):
                        image_url = ''
            qty = ln.qty or Decimal('0')
            price = ln.unit_price or Decimal('0')
            amount = qty * price
            total_qty += qty
            total_amount += amount
            if ln.expected_date and (expected is None or ln.expected_date > expected):
                expected = ln.expected_date
            if ln.payment_method:
                pay_key = ln.payment_method
            rows.append({
                'name': ln.material_name or (mat.name if mat else ln.material_code),
                'image_url': image_url,
                'spec': ' / '.join(spec),
                'unit': unit,
                'qty': qty,
                'price': price,
                'amount': amount,
                'note': '' if (ln.notes or '').strip() == (getattr(pr.sales_order, 'code', None) or '') else (ln.notes or ''),
            })
        sheets.append({
            'supplier_name': supplier.name if supplier else '',
            'supplier_contact': ' — '.join(
                bit for bit in [
                    supplier.contact_name if supplier else '',
                    supplier.phone if supplier else '',
                ] if bit
            ),
            'supplier_address': supplier.address if supplier else '',
            'supplier_tax': supplier.tax_code if supplier else '',
            'doc_code': pr.code,
            'doc_date': pr.request_date or (pr.created_at.date() if pr.created_at else timezone.localdate()),
            'rows': rows,
            'total_qty': total_qty,
            'total_amount': total_amount,
            'payment_label': pay_labels.get(pay_key or pr.payment_method, ''),
            'expected_date': expected or pr.due_date,
            'notes': '' if (pr.notes or '').strip() == (getattr(pr.sales_order, 'code', None) or '') else pr.notes,
            'order_code': getattr(pr.sales_order, 'code', '') or '',
            'preparer_name': _person_name(pr.created_by),
        })
    return render(request, 'san_xuat/print/po_a4.html', {
        **_print_base_ctx(
            print_title=f'Đơn đặt hàng {pr.code}',
            back_url=reverse('san_xuat:npl_purchase_request_detail', args=[pr.pk]),
            signature_key='po',
            doc_code=pr.code,
            doc_date=pr.request_date or timezone.localdate(),
            request=request,
        ),
        'sheets': sheets,
    })
