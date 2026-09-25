"""Yêu cầu hủy lệnh / kế hoạch sản xuất. Chỉ hủy sau khi người khác duyệt."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from san_xuat.hub_models import (
    SxFgReceiptRequest,
    SxMaterialIssueRequest,
    SxOrderTeamDayPlan,
    SxProductionCancelRequest,
    SxProductionOrder,
    SxProductionStat,
    SxSalesOrder,
    SxSubcontractOrder,
    SxTeamWorkClose,
    SxWipHandover,
)


class CancelError(Exception):
    pass


def warnings_for_mo(mo: SxProductionOrder) -> list[str]:
    notes: list[str] = []
    if mo.status == SxProductionOrder.STATUS_IN_PROGRESS:
        notes.append(f'{mo.code} đang sản xuất.')
    elif mo.status == SxProductionOrder.STATUS_DONE:
        notes.append(f'{mo.code} đã hoàn thành.')
    if SxProductionStat.objects.filter(
        production_order=mo,
        is_demo=False,
        status=SxProductionStat.STATUS_CONFIRMED,
    ).exists():
        notes.append(f'{mo.code} đã có thống kê sản xuất xác nhận.')
    issued = (
        SxMaterialIssueRequest.objects.filter(production_order=mo, is_demo=False)
        .exclude(status__in=('draft', 'cancelled'))
        .exists()
        or SxMaterialIssueRequest.objects.filter(
            production_order=mo,
            is_demo=False,
            stock_issue_id__isnull=False,
        ).exists()
    )
    if issued:
        notes.append(f'{mo.code} đã có yêu cầu hoặc phiếu xuất vật tư. Hủy không hoàn kho.')
    if (
        SxFgReceiptRequest.objects.filter(production_order=mo, is_demo=False)
        .exclude(status=SxFgReceiptRequest.STATUS_CANCELLED)
        .exists()
    ):
        notes.append(f'{mo.code} đã có yêu cầu nhập thành phẩm.')
    if SxWipHandover.objects.filter(production_order=mo, is_demo=False).exclude(
        status=SxWipHandover.STATUS_REJECTED,
    ).exists():
        notes.append(f'{mo.code} đã có bàn giao bán thành phẩm.')
    return notes


def warnings_for_plan(order: SxSalesOrder) -> list[str]:
    notes: list[str] = []
    if order.plan_status == SxSalesOrder.PLAN_DONE:
        notes.append(f'{order.code} đã hoàn thành kế hoạch.')
    elif order.plan_status == SxSalesOrder.PLAN_IN_PROGRESS:
        notes.append(f'{order.code} đang sản xuất.')
    mos = list(
        order.production_orders.filter(is_demo=False).exclude(
            status=SxProductionOrder.STATUS_CANCELLED,
        )
    )
    for mo in mos:
        notes.extend(warnings_for_mo(mo))
    if not notes and mos:
        notes.append(f'Hủy kế hoạch sẽ hủy {len(mos)} lệnh sản xuất đang hiệu lực.')
    return notes


def pending_for_mo(mo_id: int) -> SxProductionCancelRequest | None:
    return (
        SxProductionCancelRequest.objects.filter(
            target_type=SxProductionCancelRequest.TARGET_MO,
            production_order_id=mo_id,
            status=SxProductionCancelRequest.STATUS_PENDING,
        )
        .select_related('requested_by')
        .first()
    )


def pending_plan_order_ids() -> set[int]:
    return set(
        SxProductionCancelRequest.objects.filter(
            target_type=SxProductionCancelRequest.TARGET_PLAN,
            status=SxProductionCancelRequest.STATUS_PENDING,
        ).values_list('sales_order_id', flat=True)
    )


def _require_reason(reason: str) -> str:
    text = (reason or '').strip()
    if len(text) < 100:
        raise CancelError('Vui lòng nhập đầy đủ lý do.')
    return text[:2000]


@transaction.atomic
def submit_mo_cancel(*, mo: SxProductionOrder, reason: str, user) -> SxProductionCancelRequest:
    if mo.status == SxProductionOrder.STATUS_CANCELLED:
        raise CancelError('Lệnh đã hủy.')
    if pending_for_mo(mo.pk):
        raise CancelError('Lệnh đang có yêu cầu hủy chờ duyệt.')
    text = _require_reason(reason)
    notes = warnings_for_mo(mo)
    return SxProductionCancelRequest.objects.create(
        target_type=SxProductionCancelRequest.TARGET_MO,
        production_order=mo,
        sales_order_id=mo.sales_order_id,
        reason=text,
        warning_text='\n'.join(notes),
        requested_by=user,
    )


@transaction.atomic
def submit_plan_cancel(*, order: SxSalesOrder, reason: str, user) -> SxProductionCancelRequest:
    if order.plan_status == SxSalesOrder.PLAN_CANCELLED:
        raise CancelError('Kế hoạch đã hủy.')
    if order.pk in pending_plan_order_ids():
        raise CancelError('Kế hoạch đang có yêu cầu hủy chờ duyệt.')
    text = _require_reason(reason)
    notes = warnings_for_plan(order)
    return SxProductionCancelRequest.objects.create(
        target_type=SxProductionCancelRequest.TARGET_PLAN,
        sales_order=order,
        reason=text,
        warning_text='\n'.join(notes),
        requested_by=user,
    )


def _apply_mo_cancel(mo: SxProductionOrder) -> None:
    if mo.status == SxProductionOrder.STATUS_CANCELLED:
        return
    mo.status = SxProductionOrder.STATUS_CANCELLED
    mo.save(update_fields=['status'])
    SxTeamWorkClose.objects.filter(production_order_id=mo.pk).delete()
    SxSubcontractOrder.objects.filter(production_order_id=mo.pk).update(production_order=None)


def _apply_plan_cancel(order: SxSalesOrder) -> None:
    order.plan_status = SxSalesOrder.PLAN_CANCELLED
    order.plan_rank = None
    order.plan_hold_reason = ''
    order.save(update_fields=['plan_status', 'plan_rank', 'plan_hold_reason', 'updated_at'])
    mos = list(
        order.production_orders.filter(is_demo=False)
        .exclude(status=SxProductionOrder.STATUS_CANCELLED)
        .select_for_update()
    )
    for mo in mos:
        _apply_mo_cancel(mo)
    SxOrderTeamDayPlan.objects.filter(sales_order_id=order.pk).delete()
    from kho_npl.services.reservation import release_reservations_for_khsx_order

    release_reservations_for_khsx_order(order=order)


@transaction.atomic
def approve_cancel(*, request_id: int, user) -> SxProductionCancelRequest:
    req = SxProductionCancelRequest.objects.select_for_update().get(pk=request_id)
    if req.status != SxProductionCancelRequest.STATUS_PENDING:
        raise CancelError('Yêu cầu không còn chờ duyệt.')
    if req.target_type == SxProductionCancelRequest.TARGET_MO:
        mo = SxProductionOrder.objects.select_for_update().get(pk=req.production_order_id)
        _apply_mo_cancel(mo)
        if mo.sales_order_id:
            from san_xuat.services.plan_board import sync_plan_status

            order = SxSalesOrder.objects.select_for_update().get(pk=mo.sales_order_id)
            if order.plan_status != SxSalesOrder.PLAN_CANCELLED:
                sync_plan_status(order)
    else:
        order = SxSalesOrder.objects.select_for_update().get(pk=req.sales_order_id)
        _apply_plan_cancel(order)
    req.status = SxProductionCancelRequest.STATUS_APPROVED
    req.reviewed_by = user
    req.reviewed_at = timezone.now()
    req.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])
    return req


@transaction.atomic
def reject_cancel(*, request_id: int, user) -> SxProductionCancelRequest:
    req = SxProductionCancelRequest.objects.select_for_update().get(pk=request_id)
    if req.status != SxProductionCancelRequest.STATUS_PENDING:
        raise CancelError('Yêu cầu không còn chờ duyệt.')
    req.status = SxProductionCancelRequest.STATUS_REJECTED
    req.reviewed_by = user
    req.reviewed_at = timezone.now()
    req.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])
    return req
