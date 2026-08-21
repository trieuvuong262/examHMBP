from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from kho_npl.choices import DOC_STATUS_DRAFT, DOC_STATUS_POSTED
from kho_npl.models import StockBalance, StockIssue, StockLedger
from kho_npl.services.batches import (
    BatchWorkflowError,
    batch_effective_price,
    decrease_batch_qty,
    ledger_amount,
    resolve_outflow_batches,
)


class IssueWorkflowError(Exception):
    pass


def issue_is_editable(issue: StockIssue) -> bool:
    return issue.status == DOC_STATUS_DRAFT


@transaction.atomic
def post_stock_issue(issue: StockIssue, user) -> StockIssue:
    issue = StockIssue.objects.select_for_update().get(pk=issue.pk)
    if issue.status != DOC_STATUS_DRAFT:
        raise IssueWorkflowError('Chỉ phiếu đã tạo mới được xuất kho.')
    lines = list(issue.lines.select_related('material', 'location', 'batch').all())
    if not lines:
        raise IssueWorkflowError('Phiếu xuất chưa có dòng chi tiết.')
    if not issue.attachment:
        raise IssueWorkflowError('Vui lòng đính kèm chứng từ trước khi xuất kho.')
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
                f'Tồn không đủ: {line.material.code} tại {line.location.display_label()} '
                f'(có {available}, cần xuất {line.quantity}).'
            )

        try:
            allocations = resolve_outflow_batches(line.material, line.quantity, line.batch)
        except BatchWorkflowError as exc:
            raise IssueWorkflowError(str(exc)) from exc

        # Snapshot giá xuất = giá lô đầu (FIFO); gắn lô chính lên dòng phiếu
        primary_batch = allocations[0][0]
        line.batch = primary_batch
        line.unit_price = batch_effective_price(primary_batch)
        line.save(update_fields=['batch', 'unit_price'])

        running = balance.quantity
        for batch, take in allocations:
            try:
                decrease_batch_qty(batch, take, material_code=line.material.code)
            except BatchWorkflowError as exc:
                raise IssueWorkflowError(str(exc)) from exc
            running -= take
            unit_price = batch_effective_price(batch)
            StockLedger.objects.create(
                material=line.material,
                location=line.location,
                qty_delta=-take,
                balance_after=running,
                batch=batch,
                unit_price=unit_price,
                amount=ledger_amount(take, unit_price),
                ref_type=StockLedger.REF_ISSUE,
                ref_id=issue.pk,
                ref_number=issue.number,
                created_by=user,
                notes=f'Xuất kho {issue.number}',
            )
        balance.quantity = running
        balance.save(update_fields=['quantity', 'updated_at'])
    issue.status = DOC_STATUS_POSTED
    issue.posted_at = timezone.now()
    issue.save(update_fields=['status', 'posted_at'])
    return issue


@transaction.atomic
def cancel_stock_issue(issue: StockIssue) -> StockIssue:
    issue = StockIssue.objects.select_for_update().get(pk=issue.pk)
    if issue.status != DOC_STATUS_DRAFT:
        raise IssueWorkflowError('Chỉ phiếu đã tạo mới được hủy.')
    from kho_npl.choices import DOC_STATUS_CANCELLED
    issue.status = DOC_STATUS_CANCELLED
    issue.save(update_fields=['status'])
    return issue
