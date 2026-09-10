"""Màn in phiếu kho NPL A5 — cùng pattern autoprint với san_xuat."""

from __future__ import annotations

from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone

from assessment.decorators import module_perm_required
from hrm.module_permissions import MODULE_KHO_NPL
from kho_npl.models import (
    StockAdjustment,
    StockDisposal,
    StockIssue,
    StockReceipt,
    StockTransfer,
)
from san_xuat.print_company import (
    COMPANY_ADDRESS,
    COMPANY_NAME,
    COMPANY_TAX_CODE,
)

DEFAULT_SIGNATURES = (
    'Người lập',
    'Thủ kho',
    'Người nhận',
    'Xác nhận',
)

SIGNATURES = {
    'issue': DEFAULT_SIGNATURES,
    'receipt': (
        'Người lập',
        'Người nhập',
        'Người kiểm',
        'Thủ kho',
    ),
    'transfer': (
        'Người lập',
        'Kho gửi',
        'Kho nhận',
        'Xác nhận',
    ),
    'disposal': (
        'Người lập',
        'Thủ kho',
        'Người duyệt',
        'Xác nhận',
    ),
    'adjustment': (
        'Người đề xuất',
        'Thủ kho',
        'Người duyệt',
        'Xác nhận',
    ),
}


def _print_base_ctx(
    *,
    print_title: str,
    back_url: str,
    doc_date,
    request,
    doc_code: str = '',
    signature_key: str = 'issue',
):
    return {
        'print_title': print_title,
        'back_url': back_url,
        'company_name': COMPANY_NAME,
        'company_tax_code': COMPANY_TAX_CODE,
        'company_address': COMPANY_ADDRESS,
        'signature_roles': SIGNATURES.get(signature_key, DEFAULT_SIGNATURES),
        'doc_code': doc_code,
        'doc_date': doc_date,
        'printed_at': timezone.localtime(),
        'autoprint': (request.GET.get('autoprint') or '') in ('1', 'true', 'yes'),
    }


def print_url(name: str, pk: int) -> str:
    return reverse(f'kho_npl:{name}', args=[pk]) + '?autoprint=1'


@module_perm_required(MODULE_KHO_NPL, 'view')
def print_issue(request, pk: int):
    issue = get_object_or_404(
        StockIssue.objects.select_related(
            'issued_by',
            'created_by',
            'recipient',
            'recipient__profile',
        ).prefetch_related(
            'lines__material',
            'lines__material__unit',
            'lines__location',
            'lines__line_unit',
        ),
        pk=pk,
    )
    return render(request, 'kho_npl/print/issue_a5.html', {
        **_print_base_ctx(
            print_title=f'In phiếu xuất {issue.number}',
            back_url=reverse('kho_npl:issue_detail', args=[issue.pk]),
            doc_code=issue.number,
            doc_date=issue.issue_date or timezone.localdate(),
            request=request,
            signature_key='issue',
        ),
        'issue': issue,
        'lines': list(issue.lines.all()),
    })


@module_perm_required(MODULE_KHO_NPL, 'view')
def print_receipt(request, pk: int):
    receipt = get_object_or_404(
        StockReceipt.objects.select_related(
            'supplier',
            'received_by',
            'checked_by',
            'created_by',
        ).prefetch_related(
            'lines__material',
            'lines__material__unit',
            'lines__location',
            'lines__line_unit',
        ),
        pk=pk,
    )
    return render(request, 'kho_npl/print/receipt_a5.html', {
        **_print_base_ctx(
            print_title=f'In phiếu nhập {receipt.number}',
            back_url=reverse('kho_npl:receipt_detail', args=[receipt.pk]),
            doc_code=receipt.number,
            doc_date=receipt.receipt_date or timezone.localdate(),
            request=request,
            signature_key='receipt',
        ),
        'receipt': receipt,
        'lines': list(receipt.lines.all()),
    })


@module_perm_required(MODULE_KHO_NPL, 'view')
def print_transfer(request, pk: int):
    transfer = get_object_or_404(
        StockTransfer.objects.select_related(
            'from_location',
            'to_location',
            'created_by',
            'sent_by',
            'received_by',
        ).prefetch_related(
            'lines__material',
            'lines__material__unit',
            'lines__line_unit',
        ),
        pk=pk,
    )
    return render(request, 'kho_npl/print/transfer_a5.html', {
        **_print_base_ctx(
            print_title=f'In phiếu chuyển {transfer.number}',
            back_url=reverse('kho_npl:transfer_detail', args=[transfer.pk]),
            doc_code=transfer.number,
            doc_date=transfer.transfer_date or timezone.localdate(),
            request=request,
            signature_key='transfer',
        ),
        'transfer': transfer,
        'lines': list(transfer.lines.all()),
    })


@module_perm_required(MODULE_KHO_NPL, 'view')
def print_disposal(request, pk: int):
    disposal = get_object_or_404(
        StockDisposal.objects.select_related(
            'created_by',
            'posted_by',
        ).prefetch_related(
            'lines__material',
            'lines__material__unit',
            'lines__location',
            'lines__line_unit',
        ),
        pk=pk,
    )
    return render(request, 'kho_npl/print/disposal_a5.html', {
        **_print_base_ctx(
            print_title=f'In phiếu hủy {disposal.number}',
            back_url=reverse('kho_npl:disposal_detail', args=[disposal.pk]),
            doc_code=disposal.number,
            doc_date=disposal.disposal_date or timezone.localdate(),
            request=request,
            signature_key='disposal',
        ),
        'disposal': disposal,
        'lines': list(disposal.lines.all()),
    })


@module_perm_required(MODULE_KHO_NPL, 'view')
def print_adjustment(request, pk: int):
    adjustment = get_object_or_404(
        StockAdjustment.objects.select_related(
            'proposed_by',
            'approved_by',
        ).prefetch_related(
            'lines__material',
            'lines__material__unit',
            'lines__location',
            'lines__line_unit',
        ),
        pk=pk,
    )
    return render(request, 'kho_npl/print/adjustment_a5.html', {
        **_print_base_ctx(
            print_title=f'In phiếu kiểm kê {adjustment.number}',
            back_url=reverse('kho_npl:adjustment_detail', args=[adjustment.pk]),
            doc_code=adjustment.number,
            doc_date=adjustment.adjust_date or timezone.localdate(),
            request=request,
            signature_key='adjustment',
        ),
        'adjustment': adjustment,
        'lines': list(adjustment.lines.all()),
    })
