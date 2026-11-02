"""Báo sản lượng GC (GĐ2): đối tác báo ngày × size → QC duyệt → ghi tiến độ tổ thuê."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from san_xuat.hub_models import SxSubcontractOrder
from san_xuat.partner_models import GcOutputReport, GcPartnerAccount

ZERO = Decimal('0')
OPEN_STATUSES = (SxSubcontractOrder.STATUS_DRAFT, SxSubcontractOrder.STATUS_SENT)


class GcOutputError(Exception):
    pass


def _q(value) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        raise GcOutputError('Số lượng không hợp lệ.')


def partner_orders(partner):
    return (
        SxSubcontractOrder.objects.filter(partner=partner, is_demo=False)
        .exclude(status=SxSubcontractOrder.STATUS_CANCELLED)
        .select_related('production_order', 'sales_order')
    )


def reported_totals(order) -> dict:
    """Tổng SL đã báo (chờ + duyệt) và đã duyệt của phiếu."""
    pending = approved = ZERO
    for r in order.output_reports.exclude(status=GcOutputReport.STATUS_REJECTED):
        if r.status == GcOutputReport.STATUS_APPROVED:
            approved += r.approved_qty
        else:
            pending += r.total_qty
    return {'pending': pending, 'approved': approved, 'reported': pending + approved}


def accept_order(*, order, account: GcPartnerAccount) -> None:
    if order.partner_id != account.partner_id:
        raise GcOutputError('Phiếu không thuộc đối tác.')
    if order.partner_accepted_at:
        return
    if order.status not in OPEN_STATUSES:
        raise GcOutputError('Phiếu đã đóng.')
    order.partner_accepted_at = timezone.now()
    order.save(update_fields=['partner_accepted_at'])

@transaction.atomic
def submit_report(*, order_id: int, account: GcPartnerAccount, work_date, size_qtys: dict, note: str = '') -> GcOutputReport:
    order = SxSubcontractOrder.objects.select_for_update().get(pk=order_id)
    if order.partner_id != account.partner_id:
        raise GcOutputError('Phiếu không thuộc đối tác.')
    if order.status not in OPEN_STATUSES:
        raise GcOutputError('Phiếu đã đóng — không báo thêm sản lượng.')
    if not order.partner_accepted_at:
        raise GcOutputError('Hãy bấm "Nhận đơn" trước khi báo sản lượng.')
    today = timezone.localdate()
    if work_date is None or work_date > today:
        raise GcOutputError('Ngày sản xuất không được ở tương lai.')
    if work_date < order.order_date:
        raise GcOutputError('Ngày sản xuất trước ngày lập phiếu.')
    clean = {}
    for size, raw in (size_qtys or {}).items():
        q = _q(raw)
        if q < 0:
            raise GcOutputError('Số lượng không được âm.')
        if q > 0:
            clean[str(size)] = q
    if not clean:
        raise GcOutputError('Nhập ít nhất một size có số lượng > 0.')
    total = sum(clean.values(), ZERO)
    done = reported_totals(order)['reported']
    if done + total > order.qty:
        raise GcOutputError(
            f'Vượt SL phiếu: đã báo {done:,.0f}, phiếu {order.qty:,.0f}, còn được báo {max(order.qty - done, ZERO):,.0f}.'
        )
    return GcOutputReport.objects.create(
        order=order,
        partner_id=order.partner_id,
        account=account,
        work_date=work_date,
        size_qtys={k: str(v) for k, v in clean.items()},
        total_qty=total,
        note=(note or '').strip()[:255],
    )


@transaction.atomic
def cancel_report(*, report_id: int, account: GcPartnerAccount) -> None:
    report = GcOutputReport.objects.select_for_update().get(pk=report_id, partner_id=account.partner_id)
    if report.status != GcOutputReport.STATUS_SUBMITTED:
        raise GcOutputError('Chỉ huỷ được báo cáo đang chờ duyệt.')
    report.delete()


def _close_if_done(order, *, user) -> None:
    """Đủ SL duyệt = SL phiếu → hoàn thành phiếu (đóng tổ nếu đủ)."""
    approved = reported_totals(order)['approved']
    if approved < order.qty:
        return
    from san_xuat.services.phase3 import Phase3Error, receive_subcontract_goods

    try:
        receive_subcontract_goods(order_id=order.pk, qty_received=approved, user=user)
    except Phase3Error:
        pass


def _sync_order_received(order) -> None:
    approved = reported_totals(order)['approved']
    order.qty_received = approved
    fields = ['qty_received']
    if order.unit_price > 0:
        order.service_fee = (order.unit_price * approved).quantize(Decimal('0.01'))
        fields.append('service_fee')
    order.save(update_fields=fields)


@transaction.atomic
def approve_report(*, report_id: int, user, size_qtys: dict | None = None, note: str = '') -> GcOutputReport:
    """QC duyệt (có thể chỉnh SL đạt theo size ≤ SL báo) → ghi tiến độ tổ ngày SX."""
    from san_xuat.services.subcontract_progress import post_report_progress

    report = GcOutputReport.objects.select_for_update().get(pk=report_id)
    if report.status != GcOutputReport.STATUS_SUBMITTED:
        raise GcOutputError('Báo cáo không ở trạng thái chờ duyệt.')
    order = SxSubcontractOrder.objects.select_for_update().get(pk=report.order_id)
    if order.status == SxSubcontractOrder.STATUS_CANCELLED:
        raise GcOutputError('Phiếu GC đã huỷ.')
    reported = {k: _q(v) for k, v in (report.size_qtys or {}).items()}
    approved = {}
    for size, rep in reported.items():
        raw = (size_qtys or {}).get(size, rep)
        q = _q(raw)
        if q < 0 or q > rep:
            raise GcOutputError(f'SL duyệt size {size} phải từ 0 đến {rep:,.0f}.')
        if q > 0:
            approved[size] = q
    posted = post_report_progress(order=order, day=report.work_date, size_qtys=approved, user=user)
    report.status = GcOutputReport.STATUS_APPROVED
    report.approved_size_qtys = {k: str(v) for k, v in approved.items()}
    report.approved_qty = sum(approved.values(), ZERO)
    report.progress_posted = {k: str(v) for k, v in posted.items()}
    report.reviewed_by = user if getattr(user, 'pk', None) else None
    report.reviewed_at = timezone.now()
    report.review_note = (note or '').strip()[:255]
    report.save()
    if order.status == SxSubcontractOrder.STATUS_DRAFT:
        order.status = SxSubcontractOrder.STATUS_SENT
        order.sent_at = order.sent_at or timezone.now()
        order.save(update_fields=['status', 'sent_at'])
    _sync_order_received(order)
    _close_if_done(order, user=user)
    return report


@transaction.atomic
def reject_report(*, report_id: int, user, note: str = '') -> GcOutputReport:
    report = GcOutputReport.objects.select_for_update().get(pk=report_id)
    if report.status != GcOutputReport.STATUS_SUBMITTED:
        raise GcOutputError('Báo cáo không ở trạng thái chờ duyệt.')
    if not (note or '').strip():
        raise GcOutputError('Nhập lý do từ chối.')
    report.status = GcOutputReport.STATUS_REJECTED
    report.reviewed_by = user if getattr(user, 'pk', None) else None
    report.reviewed_at = timezone.now()
    report.review_note = note.strip()[:255]
    report.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_note'])
    return report


@transaction.atomic
def unapprove_report(*, report_id: int, user) -> GcOutputReport:
    """Huỷ duyệt: trừ tiến độ đã ghi, đưa báo cáo về chờ duyệt. Phiếu đã hoàn thành thì mở lại."""
    from san_xuat.services.subcontract_progress import revert_report_progress

    report = GcOutputReport.objects.select_for_update().get(pk=report_id)
    if report.status != GcOutputReport.STATUS_APPROVED:
        raise GcOutputError('Báo cáo chưa duyệt.')
    order = SxSubcontractOrder.objects.select_for_update().get(pk=report.order_id)
    revert_report_progress(order=order, day=report.work_date, posted=report.progress_posted or {}, user=user)
    report.status = GcOutputReport.STATUS_SUBMITTED
    report.approved_size_qtys = {}
    report.approved_qty = ZERO
    report.progress_posted = {}
    report.reviewed_by = None
    report.reviewed_at = None
    report.save()
    if order.status in (SxSubcontractOrder.STATUS_RECEIVED, SxSubcontractOrder.STATUS_DONE):
        from san_xuat.services.planning import PlanningError
        from san_xuat.services.team_work import is_team_job_closed, reopen_team_job

        order.status = SxSubcontractOrder.STATUS_SENT
        order.received_at = None
        order.save(update_fields=['status', 'received_at'])
        mo = order.production_order
        slug = (order.team_slug or '').strip().lower()
        if mo is not None and slug and is_team_job_closed(mo_id=mo.pk, team_slug=slug):
            try:
                reopen_team_job(mo_id=mo.pk, team_slug=slug)
            except PlanningError:
                pass
    _sync_order_received(order)
    return report
