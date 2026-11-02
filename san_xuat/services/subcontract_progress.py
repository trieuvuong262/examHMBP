"""Thuê GC ↔ tiến độ tổ: SL nhận GC ghi vào phiếu tiến độ tổ như một tổ sản xuất.

- Nhận hàng: cộng SL nhận (chia theo size kế hoạch) vào ngày nhận của tổ Ob thuê.
- Huỷ nhận: trừ đúng phần đã cộng (``progress_posted``).
- Phiếu tách ngày (``plan_date``) chỉ đóng tổ khi tổ đã đủ SL; phiếu cả công đoạn đóng ngay.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.utils import timezone

from san_xuat.hub_models import SxProductionOrder, SxSubcontractOrder, SxTeamProgressLog

ZERO = Decimal('0')


def _q(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal('0.01'))


def _team_ctx(mo: SxProductionOrder, slug: str):
    from san_xuat.services.order_progress_sheet import (
        progress_steps_for_team,
        team_size_qty_by_day,
        team_size_rollups,
    )
    from san_xuat.services.progress_template import team_by_slug

    meta = team_by_slug(slug)
    if not meta:
        return None, [], {}, {}
    steps = progress_steps_for_team(mo, meta)
    if not steps:
        return meta, [], {}, {}
    rollups = team_size_rollups(mo, steps=steps, team=meta)
    by_day = team_size_qty_by_day(mo, steps=steps, team=meta)
    return meta, steps, rollups, by_day


def _write_day(
    *,
    mo: SxProductionOrder,
    slug: str,
    steps,
    day: date,
    targets: dict[str, Decimal],
    current: dict[str, Decimal],
    user,
) -> None:
    from san_xuat.services.order_progress_sheet import set_team_day_qtys
    from san_xuat.services.team_progress_log import log_day_change

    payload = [(size, qty) for size, qty in targets.items() if qty != current.get(size, ZERO)]
    if not payload:
        return
    set_team_day_qtys(
        mo_id=mo.pk,
        process_keys=[s.key for s in steps],
        size_qtys=payload,
        user=user,
        team_slug=slug,
        stat_date=day,
        allow_future=True,
    )
    for size, new in payload:
        log_day_change(
            mo=mo,
            team_slug=slug,
            work_date=day,
            size_label=size,
            old_qty=current.get(size, ZERO),
            new_qty=new,
            user=user,
            kind=SxTeamProgressLog.KIND_GC,
        )


def post_gc_progress(*, order: SxSubcontractOrder, qty: Decimal, user=None) -> dict[str, Decimal]:
    """Cộng SL nhận GC vào tiến độ tổ (ngày nhận). Trả về {size: SL đã cộng}."""
    from san_xuat.services.order_progress_sheet import allocate_qty_by_weight

    mo = order.production_order
    slug = (order.team_slug or '').strip().lower()
    qty = _q(qty)
    if mo is None or not slug or qty <= 0 or order.progress_posted:
        return {}
    if mo.status in (SxProductionOrder.STATUS_DRAFT, SxProductionOrder.STATUS_CANCELLED):
        return {}
    _meta, steps, rollups, by_day = _team_ctx(mo, slug)
    if not steps or not rollups:
        return {}
    remain_total = sum((row['remain'] for row in rollups.values()), ZERO)
    take = min(qty, remain_total)
    if take <= 0:
        return {}
    weights = [(size, row['remain']) for size, row in rollups.items() if row['remain'] > 0]
    parts = allocate_qty_by_weight(take, weights)
    parts = {size: q for size, q in parts.items() if q > 0}
    if not parts:
        return {}
    day = timezone.localdate()
    current = dict(by_day.get(day, {}))
    targets = {size: current.get(size, ZERO) + q for size, q in parts.items()}
    _write_day(mo=mo, slug=slug, steps=steps, day=day, targets=targets, current=current, user=user)
    order.progress_date = day
    order.progress_posted = {size: str(q) for size, q in parts.items()}
    order.save(update_fields=['progress_date', 'progress_posted'])
    return parts


def revert_gc_progress(*, order: SxSubcontractOrder, user=None) -> None:
    """Trừ lại phần SL đã cộng khi nhận GC."""
    mo = order.production_order
    slug = (order.team_slug or '').strip().lower()
    posted = order.progress_posted or {}
    day = order.progress_date
    if mo is not None and slug and posted and day and mo.status not in (
        SxProductionOrder.STATUS_DRAFT,
        SxProductionOrder.STATUS_CANCELLED,
    ):
        _meta, steps, _rollups, by_day = _team_ctx(mo, slug)
        if steps:
            current = dict(by_day.get(day, {}))
            targets = {
                size: max(current.get(size, ZERO) - _q(q), ZERO)
                for size, q in posted.items()
            }
            _write_day(mo=mo, slug=slug, steps=steps, day=day, targets=targets, current=current, user=user)
    order.progress_date = None
    order.progress_posted = {}
    order.save(update_fields=['progress_date', 'progress_posted'])


def team_size_status(order: SxSubcontractOrder) -> dict[str, dict]:
    """{size: {plan, done, remain}} của tổ thuê trên LSX — dùng cho form báo SL đối tác."""
    mo = order.production_order
    slug = (order.team_slug or '').strip().lower()
    if mo is None or not slug:
        return {}
    _meta, steps, rollups, _by_day = _team_ctx(mo, slug)
    return rollups if steps else {}


def post_report_progress(
    *, order: SxSubcontractOrder, day: date, size_qtys: dict[str, Decimal], user=None,
) -> dict[str, Decimal]:
    """Cộng SL duyệt (theo size) vào tiến độ tổ ngày `day`; mỗi size chặn ở phần còn lại."""
    mo = order.production_order
    slug = (order.team_slug or '').strip().lower()
    if mo is None or not slug:
        return {}
    if mo.status in (SxProductionOrder.STATUS_DRAFT, SxProductionOrder.STATUS_CANCELLED):
        return {}
    _meta, steps, rollups, by_day = _team_ctx(mo, slug)
    if not steps or not rollups:
        return {}
    parts: dict[str, Decimal] = {}
    for size, raw in size_qtys.items():
        row = rollups.get(size)
        if row is None:
            continue
        take = min(_q(raw), row['remain'])
        if take > 0:
            parts[size] = take
    if not parts:
        return {}
    current = dict(by_day.get(day, {}))
    targets = {size: current.get(size, ZERO) + q for size, q in parts.items()}
    _write_day(mo=mo, slug=slug, steps=steps, day=day, targets=targets, current=current, user=user)
    return parts


def revert_report_progress(
    *, order: SxSubcontractOrder, day: date, posted: dict, user=None,
) -> None:
    mo = order.production_order
    slug = (order.team_slug or '').strip().lower()
    if mo is None or not slug or not posted or mo.status in (
        SxProductionOrder.STATUS_DRAFT,
        SxProductionOrder.STATUS_CANCELLED,
    ):
        return
    _meta, steps, _rollups, by_day = _team_ctx(mo, slug)
    if not steps:
        return
    current = dict(by_day.get(day, {}))
    targets = {size: max(current.get(size, ZERO) - _q(q), ZERO) for size, q in posted.items()}
    _write_day(mo=mo, slug=slug, steps=steps, day=day, targets=targets, current=current, user=user)


def team_fully_done(*, mo: SxProductionOrder, slug: str) -> bool:
    _meta, steps, rollups, _by_day = _team_ctx(mo, slug)
    if not steps or not rollups:
        return False
    return all(row['remain'] <= 0 for row in rollups.values())


def should_close_team(*, order: SxSubcontractOrder, mo: SxProductionOrder, slug: str) -> bool:
    """Phiếu cả công đoạn → đóng tổ. Phiếu tách ngày → chỉ đóng khi tổ đủ SL."""
    if not order.plan_date:
        return True
    return team_fully_done(mo=mo, slug=slug)
