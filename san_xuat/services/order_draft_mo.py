"""LSX nháp cho đơn đã xác nhận nhưng còn Chờ xếp / Tạm giữ trên KHSX.

Mỗi mã hàng đủ BOM + công đoạn có một LSX nháp gắn đơn. Sửa đơn thì nháp đi theo;
Chuyển SX (hoặc mở lệnh nhập tiến độ) phát hành chính lệnh nháp đó, giữ mã lệnh.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from san_xuat.hub_models import SxProductionOrder, SxSalesOrder, SxSalesOrderLine

logger = logging.getLogger(__name__)

DRAFT_PLAN_STATUSES = (
    SxSalesOrder.PLAN_QUEUED,
    SxSalesOrder.PLAN_RANKED,
    SxSalesOrder.PLAN_ON_HOLD,
)

_ORDER_WATCHED_FIELDS = {
    'code', 'confirm_status', 'plan_status', 'due_date', 'request_date', 'plan_start_date',
}


def order_draft_mo_q(prefix: str = '') -> Q:
    """LSX nháp gắn đơn — chưa sản xuất, không khoá BOM / OB."""
    return Q(**{
        f'{prefix}status': SxProductionOrder.STATUS_DRAFT,
        f'{prefix}sales_order__isnull': False,
    })


def is_order_draft_mo(mo: SxProductionOrder) -> bool:
    return mo.status == SxProductionOrder.STATUS_DRAFT and bool(mo.sales_order_id)


@dataclass
class DraftMoSyncResult:
    created: int = 0
    updated: int = 0
    cancelled: int = 0

    @property
    def changed(self) -> int:
        return self.created + self.updated + self.cancelled


def _cancel(mo: SxProductionOrder, result: DraftMoSyncResult) -> None:
    mo.status = SxProductionOrder.STATUS_CANCELLED
    mo.save(update_fields=['status'])
    result.cancelled += 1


def _line_ready(ln: SxSalesOrderLine) -> bool:
    from san_xuat.services.plan_board import _line_has_operations

    bom = ln.bom_version
    if bom is None or bom.tech_doc is None:
        return False
    code = (ln.product_code or '').strip().casefold()
    if (bom.tech_doc.product_code or '').strip().casefold() != code:
        return False
    return _line_has_operations(ln, routing_id=ln.routing_id, bom=bom)


@transaction.atomic
def sync_order_draft_mos(order_id: int, *, user=None) -> DraftMoSyncResult:
    """Tạo / cập nhật / hủy LSX nháp cho đúng các dòng đơn đang chờ xếp."""
    from san_xuat.services.dispatch import DispatchError, create_mo_from_bom
    from san_xuat.services.plan_board import (
        order_line_plan_window,
        order_plan_step_maps,
        sync_mo_steps_from_order_line,
    )

    result = DraftMoSyncResult()
    order = (
        SxSalesOrder.objects.select_for_update()
        .filter(pk=order_id, is_demo=False)
        .first()
    )
    if order is None:
        return result

    drafts = list(
        SxProductionOrder.objects.select_for_update()
        .filter(sales_order_id=order.pk, is_demo=False, status=SxProductionOrder.STATUS_DRAFT)
        .order_by('pk')
    )
    is_open = (
        order.confirm_status == SxSalesOrder.CONFIRM_CONFIRMED
        and order.plan_status in DRAFT_PLAN_STATUSES
    )
    if not is_open:
        if (
            order.confirm_status != SxSalesOrder.CONFIRM_CONFIRMED
            or order.plan_status == SxSalesOrder.PLAN_CANCELLED
        ):
            for mo in drafts:
                _cancel(mo, result)
        return result

    started_codes = {
        (code or '').strip().casefold()
        for code in order.production_orders.filter(is_demo=False)
        .exclude(status__in=(SxProductionOrder.STATUS_DRAFT, SxProductionOrder.STATUS_CANCELLED))
        .values_list('product_code', flat=True)
    }
    lines = list(
        order.lines.filter(qty__gt=0)
        .select_related('bom_version__tech_doc')
        .prefetch_related('routing_lines')
        .order_by('sort_order', 'id')
    )
    wanted: dict[str, SxSalesOrderLine] = {}
    for ln in lines:
        key = (ln.product_code or '').strip().casefold()
        if not key or key in wanted or key in started_codes:
            continue
        if _line_ready(ln):
            wanted[key] = ln

    drafts_by_code: dict[str, SxProductionOrder] = {}
    for mo in drafts:
        key = (mo.product_code or '').strip().casefold()
        if key not in wanted or key in drafts_by_code:
            _cancel(mo, result)
            continue
        drafts_by_code[key] = mo

    if not wanted:
        return result

    planned_by_name, hop_by_name = order_plan_step_maps(order)
    for key, ln in wanted.items():
        due_date = ln.due_date or order.due_date
        plan_start, plan_end = order_line_plan_window(order, ln)
        mo = drafts_by_code.get(key)
        if mo is None:
            try:
                mo = create_mo_from_bom(
                    product_code=ln.product_code,
                    qty=ln.qty_to_produce,
                    order_date=timezone.localdate(),
                    due_date=due_date,
                    planned_start=plan_start,
                    planned_end=plan_end,
                    notes=f'Từ ĐĐH {order.code}',
                    user=user,
                    sales_order_id=order.pk,
                    bom_version_id=ln.bom_version_id,
                    routing_id=ln.routing_id,
                )
            except DispatchError as exc:
                logger.warning('Không tạo được LSX nháp %s / %s: %s', order.code, ln.product_code, exc)
                continue
            if ln.product_name and not mo.product_name:
                mo.product_name = ln.product_name
                mo.save(update_fields=['product_name'])
            sync_mo_steps_from_order_line(
                mo,
                ln,
                routing_id=ln.routing_id,
                planned_by_name=planned_by_name,
                hop_by_name=hop_by_name,
            )
            result.created += 1
            continue

        tech_changed = (
            mo.bom_version_id != ln.bom_version_id or mo.routing_id != ln.routing_id
        )
        fields = []
        for name, value in (
            ('qty', ln.qty_to_produce),
            ('due_date', due_date),
            ('planned_start', plan_start),
            ('planned_end', plan_end),
            ('bom_version_id', ln.bom_version_id),
            ('routing_id', ln.routing_id),
        ):
            if getattr(mo, name) != value:
                setattr(mo, name, value)
                fields.append(name)
        if fields:
            mo.save(update_fields=fields)
        if tech_changed or not mo.mo_process_steps.exists():
            sync_mo_steps_from_order_line(
                mo,
                ln,
                routing_id=ln.routing_id,
                planned_by_name=planned_by_name,
                hop_by_name=hop_by_name,
            )
        if fields or tech_changed:
            result.updated += 1
    return result


def _on_commit_marker(order_id: int):
    def _run():
        try:
            sync_order_draft_mos(order_id)
        except Exception:
            logger.exception('Đồng bộ LSX nháp lỗi cho đơn #%s', order_id)

    _run.sx_draft_mo_order_id = order_id
    return _run


def schedule_order_draft_mo_sync(order_id: int | None) -> None:
    """Đồng bộ sau commit; gộp nhiều lần lưu cùng đơn trong một transaction."""
    if not order_id:
        return
    conn = transaction.get_connection()
    if conn.in_atomic_block:
        for entry in conn.run_on_commit:
            if getattr(entry[1], 'sx_draft_mo_order_id', None) == order_id:
                return
    transaction.on_commit(_on_commit_marker(order_id))


def _on_order_saved(sender, instance, raw=False, update_fields=None, **kwargs):
    if raw or instance.is_demo:
        return
    if update_fields is not None and not (set(update_fields) & _ORDER_WATCHED_FIELDS):
        return
    schedule_order_draft_mo_sync(instance.pk)


def _on_line_changed(sender, instance, raw=False, **kwargs):
    if raw:
        return
    schedule_order_draft_mo_sync(instance.order_id)


def connect_order_draft_mo_signals() -> None:
    from django.db.models.signals import post_delete, post_save

    post_save.connect(
        _on_order_saved,
        sender=SxSalesOrder,
        dispatch_uid='sx_order_draft_mo_order_save',
    )
    post_save.connect(
        _on_line_changed,
        sender=SxSalesOrderLine,
        dispatch_uid='sx_order_draft_mo_line_save',
    )
    post_delete.connect(
        _on_line_changed,
        sender=SxSalesOrderLine,
        dispatch_uid='sx_order_draft_mo_line_delete',
    )
