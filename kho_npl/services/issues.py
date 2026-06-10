from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from kho_npl.choices import DOC_STATUS_DRAFT, DOC_STATUS_POSTED
from kho_npl.models import StockBalance, StockIssue, StockLedger


class IssueWorkflowError(Exception):
    pass


def issue_is_editable(issue: StockIssue) -> bool:
    return issue.status == DOC_STATUS_DRAFT


@transaction.atomic
def post_stock_issue(issue: StockIssue, user) -> StockIssue:
    issue = StockIssue.objects.select_for_update().get(pk=issue.pk)
    if issue.status != DOC_STATUS_DRAFT:
        raise IssueWorkflowError('Chỉ phiếu nháp mới được ghi sổ.')
    lines = list(issue.lines.select_related('material', 'location').all())
    if not lines:
        raise IssueWorkflowError('Phiếu xuất chưa có dòng chi tiết.')
    for line in lines:
        if line.quantity <= Decimal('0'):
            raise IssueWorkflowError(f'Số lượng xuất của {line.material.code} phải lớn hơn 0.')
        balance = (
            StockBalance.objects.select_for_update()
            .filter(material=line.material, location=line.location)
            .first()
        )
        available = balance.quantity if balance else Decimal('0')
        if available < line.quantity:
            raise IssueWorkflowError(
                f'Tồn không đủ: {line.material.code} tại {line.location.code} '
                f'(có {available}, cần xuất {line.quantity}).'
            )
        balance.quantity -= line.quantity
        balance.save(update_fields=['quantity', 'updated_at'])
        StockLedger.objects.create(
            material=line.material,
            location=line.location,
            qty_delta=-line.quantity,
            balance_after=balance.quantity,
            ref_type=StockLedger.REF_ISSUE,
            ref_id=issue.pk,
            ref_number=issue.number,
            created_by=user,
            notes=f'Xuất kho {issue.number}',
        )
    issue.status = DOC_STATUS_POSTED
    issue.posted_at = timezone.now()
    issue.save(update_fields=['status', 'posted_at'])
    return issue


@transaction.atomic
def cancel_stock_issue(issue: StockIssue) -> StockIssue:
    issue = StockIssue.objects.select_for_update().get(pk=issue.pk)
    if issue.status != DOC_STATUS_DRAFT:
        raise IssueWorkflowError('Chỉ phiếu nháp mới được hủy.')
    from kho_npl.choices import DOC_STATUS_CANCELLED
    issue.status = DOC_STATUS_CANCELLED
    issue.save(update_fields=['status'])
    return issue
