"""Lập đề nghị mua từ các dòng nhu cầu thiếu, không mua trùng."""

from __future__ import annotations

from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from san_xuat.hub_models import (
    SxNplPurchaseRequest,
    SxNplPurchaseRequestLine,
    SxOrderNplLine,
)
from san_xuat.services.plan_audit import log_plan_action
from san_xuat.services.planning import PlanningError, _code


def department_name_of(user) -> str:
    profile = getattr(user, 'profile', None)
    dept = getattr(profile, 'department', None) if profile is not None else None
    name = getattr(dept, 'name', '') if dept is not None else ''
    return (name or '')[:120]


_OPEN_PR = (
    SxNplPurchaseRequest.STATUS_DRAFT,
    SxNplPurchaseRequest.STATUS_PRICE_REVIEW,
    SxNplPurchaseRequest.STATUS_PRICED,
    SxNplPurchaseRequest.STATUS_SUBMITTED,
    SxNplPurchaseRequest.STATUS_APPROVED,
)


@transaction.atomic
def create_pr_from_npl_lines(*, line_ids: list[int], user=None, reason: str = '') -> list[SxNplPurchaseRequest]:
    from san_xuat.services.plan_order_npl import sync_order_npl

    ids = []
    for raw in line_ids or []:
        try:
            rid = int(raw)
        except (TypeError, ValueError):
            continue
        if rid and rid not in ids:
            ids.append(rid)
    if not ids:
        raise PlanningError('Chọn ít nhất một dòng vật tư.')
    note = (reason or '').strip()
    if not note:
        raise PlanningError('Nhập lý do đề nghị mua.')
    order_ids = list(
        SxOrderNplLine.objects.filter(pk__in=ids).values_list('order_id', flat=True).distinct()
    )
    for oid in order_ids:
        sync_order_npl(order_id=oid)
    lines = list(
        SxOrderNplLine.objects.select_related('order').filter(pk__in=ids, order__is_demo=False)
    )
    covered = set(
        SxNplPurchaseRequestLine.objects.filter(
            source_npl_line_id__in=ids,
            request__is_demo=False,
            request__status__in=_OPEN_PR,
        ).values_list('source_npl_line_id', flat=True)
    )
    groups: dict[int, list[SxOrderNplLine]] = defaultdict(list)
    for ln in lines:
        if ln.pk in covered or (ln.qty_shortfall or 0) <= 0:
            continue
        groups[ln.order_id].append(ln)
    if not groups:
        raise PlanningError(
            'Các dòng đã được tồn kho, đơn đang mở hoặc đề nghị còn hiệu lực bao phủ. Không lập mua trùng.'
        )
    dept = department_name_of(user)
    created: list[SxNplPurchaseRequest] = []
    for _oid, group in groups.items():
        order = group[0].order
        need_dates = [ln.ready_date for ln in group if ln.ready_date]
        pr = SxNplPurchaseRequest.objects.create(
            code=_code('npl_pr', SxNplPurchaseRequest),
            sales_order=order,
            request_date=timezone.localdate(),
            due_date=min(need_dates) if need_dates else None,
            status=SxNplPurchaseRequest.STATUS_DRAFT,
            reason=note[:500],
            department_name=dept,
            is_demo=False,
            created_by=user if getattr(user, 'pk', None) else None,
        )
        SxNplPurchaseRequestLine.objects.bulk_create([
            SxNplPurchaseRequestLine(
                request=pr,
                material_code=ln.material_code,
                material_name=ln.material_name,
                qty=ln.qty_shortfall,
                need_date=ln.ready_date,
                source_npl_line=ln,
            )
            for ln in group
        ])
        log_plan_action(
            action='create',
            obj=pr,
            summary=f'Tạo đề nghị {pr.code} từ {len(group)} dòng nhu cầu của {order.code}.',
            changes={'sales_order': order.code, 'lines': len(group), 'reason': note[:500]},
            user=user,
        )
        created.append(pr)
        sync_order_npl(order_id=order.pk)
    return created


@transaction.atomic
def create_pr_for_po_shortfall(*, order_id: int, user=None, reason: str = ''):
    """Lập đề nghị mua bù phần còn thiếu của đơn đã phát hành. Không đóng đơn gốc."""
    from san_xuat.hub_models import SxPurchaseOrder

    note = (reason or '').strip()
    if not note:
        raise PlanningError('Nhập lý do mua bù nhà cung cấp khác.')
    po = SxPurchaseOrder.objects.select_for_update().prefetch_related('lines').get(pk=order_id, is_demo=False)
    if po.status != SxPurchaseOrder.STATUS_CONFIRMED:
        raise PlanningError('Chỉ mua bù khi đơn đang phát hành và còn thiếu.')
    short_lines = [ln for ln in po.lines.all() if ln.qty_remaining > 0]
    if not short_lines:
        raise PlanningError('Đơn không còn số lượng thiếu.')
    sales_order = po.purchase_request.sales_order if po.purchase_request_id else None
    pr = SxNplPurchaseRequest.objects.create(
        code=_code('npl_pr', SxNplPurchaseRequest),
        sales_order=sales_order,
        request_date=timezone.localdate(),
        due_date=po.expected_date,
        status=SxNplPurchaseRequest.STATUS_DRAFT,
        reason=note[:500],
        department_name=department_name_of(user),
        notes=f'Mua bù cho đơn {po.code}'[:4000],
        is_demo=False,
        created_by=user if getattr(user, 'pk', None) else None,
    )
    SxNplPurchaseRequestLine.objects.bulk_create([
        SxNplPurchaseRequestLine(
            request=pr,
            material_code=ln.material_code,
            material_name=ln.material_name,
            qty=ln.qty_remaining,
            need_date=po.expected_date,
        )
        for ln in short_lines
    ])
    log_plan_action(
        action='create',
        obj=pr,
        summary=f'Tạo đề nghị mua bù {pr.code} từ phần thiếu của {po.code}.',
        changes={'purchase_order': po.code, 'lines': len(short_lines), 'reason': note[:500]},
        user=user,
    )
    return pr
