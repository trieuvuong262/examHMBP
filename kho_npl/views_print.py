"""Màn in phiếu kho NPL A5 — cùng pattern autoprint với san_xuat."""

from __future__ import annotations

from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone

from assessment.decorators import module_perm_required
from hrm.module_permissions import MODULE_KHO_NPL
from kho_npl.models import StockIssue
from san_xuat.print_company import (
    COMPANY_ADDRESS,
    COMPANY_NAME,
    COMPANY_TAX_CODE,
)

ISSUE_SIGNATURES = (
    'Người lập',
    'Thủ kho',
    'Người nhận',
    'Xác nhận',
)


def _print_base_ctx(*, print_title: str, back_url: str, doc_date, request, doc_code: str = ''):
    return {
        'print_title': print_title,
        'back_url': back_url,
        'company_name': COMPANY_NAME,
        'company_tax_code': COMPANY_TAX_CODE,
        'company_address': COMPANY_ADDRESS,
        'signature_roles': ISSUE_SIGNATURES,
        'doc_code': doc_code,
        'doc_date': doc_date,
        'printed_at': timezone.localtime(),
        'autoprint': (request.GET.get('autoprint') or '') in ('1', 'true', 'yes'),
    }


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
        ),
        'issue': issue,
        'lines': list(issue.lines.all()),
    })
