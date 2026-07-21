"""Màn in phiếu A5 — P0 + P1 chứng từ sản xuất."""

from __future__ import annotations

from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone

from assessment.decorators import module_perm_required
from hrm.module_permissions import MODULE_SAN_XUAT
from san_xuat.hub_models import (
    SxFgReceiptRequest,
    SxMaterialIssueRequest,
    SxNcrCase,
    SxPackingRecord,
    SxProductionOrder,
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


def _print_base_ctx(*, print_title: str, back_url: str, signature_key: str, doc_date, request):
    return {
        'print_title': print_title,
        'back_url': back_url,
        'company_name': COMPANY_NAME,
        'company_tax_code': COMPANY_TAX_CODE,
        'company_address': COMPANY_ADDRESS,
        'signature_roles': SIGNATURES[signature_key],
        'doc_date': doc_date,
        'printed_at': timezone.localtime(),
        'autoprint': (request.GET.get('autoprint') or '') in ('1', 'true', 'yes'),
    }


def _bom_lines_for_mo(mo: SxProductionOrder) -> list[dict]:
    bom_lines = []
    if not mo.bom_version_id:
        return bom_lines
    for bl in mo.bom_version.lines.all():
        qty_per_unit = bl.qty_with_scrap
        bom_lines.append({
            'material_code': bl.material.code,
            'material_name': bl.material.name,
            'qty_per_unit': qty_per_unit,
            'qty_total': qty_per_unit * (mo.qty or 0),
            'scrap_pct': bl.scrap_pct,
        })
    return bom_lines


@module_perm_required(MODULE_SAN_XUAT, 'print')
def print_mo(request, pk: int):
    mo = get_object_or_404(
        SxProductionOrder.objects.select_related('bom_version').prefetch_related(
            'bom_version__lines__material',
        ),
        pk=pk,
    )
    return render(request, 'san_xuat/print/mo_a5.html', {
        **_print_base_ctx(
            print_title=f'In LSX {mo.code}',
            back_url=reverse('san_xuat:dispatch_mo_detail', args=[mo.pk]),
            signature_key='mo',
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
            print_title=f'In YCX {req.code}',
            back_url=reverse('san_xuat:dispatch_material_issue_req_detail', args=[req.pk]),
            signature_key='ycx',
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
            'defect_lines__defect',
        ),
        pk=pk,
    )
    qc_request = inspection.qc_request
    mo = qc_request.production_order if qc_request else None
    return render(request, 'san_xuat/print/qc_a5.html', {
        **_print_base_ctx(
            print_title=f'In PKT {inspection.code}',
            back_url=reverse('san_xuat:qc_sheet_detail', args=[inspection.pk]),
            signature_key='qc',
            doc_date=inspection.inspected_at or timezone.localdate(),
            request=request,
        ),
        'inspection': inspection,
        'qc_request': qc_request,
        'mo': mo,
        'criteria_lines': list(inspection.criteria_lines.all()),
        'defect_lines': list(inspection.defect_lines.all()),
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
            print_title=f'In YCNTP {fg_req.code}',
            back_url=reverse('san_xuat:dispatch_fg_receipt_req_detail', args=[fg_req.pk]),
            signature_key='ycntp',
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
            doc_date=handover.handover_date or timezone.localdate(),
            request=request,
        ),
        'handover': handover,
        'mo': mo,
    })


@module_perm_required(MODULE_SAN_XUAT, 'print')
def print_subcontract(request, pk: int):
    item = get_object_or_404(
        SxSubcontractOrder.objects.select_related('production_order').prefetch_related(
            'material_lines',
        ),
        pk=pk,
    )
    return render(request, 'san_xuat/print/subcontract_a5.html', {
        **_print_base_ctx(
            print_title=f'In GC {item.code}',
            back_url=reverse('san_xuat:subcontract_detail', args=[item.pk]),
            signature_key='subcontract',
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
            print_title=f'In NCR {case.code}',
            back_url=reverse('san_xuat:ncr_detail', args=[case.pk]),
            signature_key='ncr',
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
            doc_date=(alert.created_at.date() if alert.created_at else timezone.localdate()),
            request=request,
        ),
        'alert': alert,
        'mo': alert.production_order,
    })
