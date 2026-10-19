"""Lịch sử sửa SL tiến độ tổ theo ngày — đánh dấu nhập bù (sửa sau ngày đó)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from san_xuat.hub_models import SxProductionOrder, SxTeamProgressLog


def log_day_change(
    *,
    mo: SxProductionOrder,
    team_slug: str,
    work_date: date,
    size_label: str,
    old_qty: Decimal,
    new_qty: Decimal,
    user,
    kind: str = SxTeamProgressLog.KIND_EDIT,
) -> SxTeamProgressLog | None:
    if Decimal(old_qty or 0) == Decimal(new_qty or 0):
        return None
    return SxTeamProgressLog.objects.create(
        production_order=mo,
        team_slug=team_slug,
        work_date=work_date,
        size_label=size_label or '',
        old_qty=old_qty or 0,
        new_qty=new_qty or 0,
        is_backfill=work_date < timezone.localdate(),
        kind=kind,
        changed_by=user if getattr(user, 'is_authenticated', False) else None,
    )


def align_closed_team_qty(
    *,
    mo: SxProductionOrder,
    team_meta: dict,
    team_slug: str,
    user,
    anchor: date | None = None,
) -> Decimal:
    """Bù SL tổ đã chốt cho khớp KH từng ngày. Phần còn thiếu ghi vào ngày chốt.

    SL đã nhập giữ nguyên: chỉ tăng công đoạn đang thiếu, không hạ số đã có.
    Trả về tổng SL tổ (theo bộ) được điền thêm.
    """
    from san_xuat.services.order_progress_sheet import (
        allocate_qty_by_weight,
        progress_steps_for_team,
        set_team_day_qtys,
        team_plan_days,
        team_size_qty_by_day,
        team_size_rollups,
    )

    steps = progress_steps_for_team(mo, team_meta)
    if not steps:
        return Decimal('0')
    rollups = team_size_rollups(mo, steps=steps, team=team_meta)
    if not rollups:
        return Decimal('0')
    remaining = {size: row['remain'] for size, row in rollups.items()}
    if all(qty <= 0 for qty in remaining.values()):
        return Decimal('0')
    today = timezone.localdate()
    anchor_day = anchor or today
    if anchor_day > today:
        anchor_day = today
    weights = [(size, row['plan']) for size, row in rollups.items()]
    plans = team_plan_days(mo, team_meta)
    by_day = team_size_qty_by_day(mo, steps=steps, team=team_meta)
    keys = [step.key for step in steps]
    slug = (team_slug or '').strip().lower()
    filled = Decimal('0')

    def _apply(day: date, targets: dict[str, Decimal]) -> None:
        nonlocal filled
        current = by_day.setdefault(day, {})
        payload: list[tuple[str, Decimal]] = []
        deltas: list[tuple[str, Decimal, Decimal, Decimal]] = []
        for size, want in targets.items():
            have = current.get(size, Decimal('0'))
            add = min(max(want - have, Decimal('0')), remaining.get(size, Decimal('0')))
            if add <= 0:
                continue
            payload.append((size, have + add))
            deltas.append((size, have, have + add, add))
        if not payload:
            return
        set_team_day_qtys(
            mo_id=mo.pk,
            process_keys=keys,
            size_qtys=payload,
            user=user,
            team_slug=slug,
            stat_date=day,
            only_increase=True,
            allow_future=True,
        )
        for size, old, new, add in deltas:
            remaining[size] = remaining.get(size, Decimal('0')) - add
            current[size] = new
            filled += add
            log_day_change(
                mo=mo,
                team_slug=slug,
                work_date=day,
                size_label=size,
                old_qty=old,
                new_qty=new,
                user=user,
                kind=SxTeamProgressLog.KIND_COMPLETE,
            )

    for day in sorted(
        plan_day for plan_day, qty in plans.items() if qty is not None and qty > 0
    ):
        _apply(day, allocate_qty_by_weight(plans[day], weights))
    if any(qty > 0 for qty in remaining.values()):
        have = by_day.get(anchor_day, {})
        _apply(anchor_day, {
            size: have.get(size, Decimal('0')) + qty
            for size, qty in remaining.items()
            if qty > 0
        })
    return filled


def fill_remaining_on_complete(*, mo: SxProductionOrder, team_meta: dict, team_slug: str, user) -> Decimal:
    """Khi tổ bấm Hoàn thành: bù phần còn thiếu cho khớp kế hoạch ngày.

    SL đã nhập giữ nguyên. Phần kế hoạch không phủ hết ghi vào hôm nay.
    """
    return align_closed_team_qty(
        mo=mo,
        team_meta=team_meta,
        team_slug=team_slug,
        user=user,
        anchor=timezone.localdate(),
    )


def backfill_closed_team_outputs() -> int:
    """Lệnh đã chốt mà SL chưa đủ kế hoạch: điền cho khớp. Trả về số lệnh đã bù."""
    from hrm.request_cache import begin, end, is_active

    from san_xuat.hub_models import SxSalesOrder, SxTeamWorkClose
    from san_xuat.services.planning import PlanningError
    from san_xuat.services.progress_template import team_by_slug

    opened = False
    if not is_active():
        begin(enabled=True)
        opened = True
    touched = 0
    try:
        closes = (
            SxTeamWorkClose.objects.filter(is_demo=False)
            .select_related('production_order', 'production_order__sales_order', 'created_by')
            .order_by('id')
        )
        seen: set[tuple[int, str]] = set()
        for rec in closes:
            mo = rec.production_order
            slug = (rec.team_slug or '').strip().lower()
            if mo is None or mo.is_demo or not slug:
                continue
            if mo.status in (
                SxProductionOrder.STATUS_CANCELLED,
                SxProductionOrder.STATUS_DRAFT,
            ):
                continue
            order = mo.sales_order if mo.sales_order_id else None
            if order is not None and order.plan_status == SxSalesOrder.PLAN_CANCELLED:
                continue
            key = (mo.pk, slug)
            if key in seen:
                continue
            seen.add(key)
            meta = team_by_slug(slug)
            if not meta:
                continue
            anchor = timezone.localtime(rec.closed_at).date() if rec.closed_at else timezone.localdate()
            try:
                filled = align_closed_team_qty(
                    mo=mo,
                    team_meta=meta,
                    team_slug=slug,
                    user=rec.created_by,
                    anchor=anchor,
                )
            except PlanningError:
                continue
            if filled > 0:
                touched += 1
    finally:
        if opened:
            end()
    return touched


@transaction.atomic
def complete_team_job(*, mo_id: int, team_meta: dict, team_slug: str, user) -> Decimal:
    """Đóng việc tổ trên lệnh + tự điền SL còn thiếu. Trả về SL đã điền thêm."""
    from san_xuat.services.team_work import close_team_job

    close_team_job(mo_id=mo_id, team_slug=team_slug, user=user)
    mo = SxProductionOrder.objects.get(pk=mo_id)
    return fill_remaining_on_complete(mo=mo, team_meta=team_meta, team_slug=team_slug, user=user)


def log_to_dict(log: SxTeamProgressLog) -> dict:
    user = log.changed_by
    return {
        'at': timezone.localtime(log.changed_at).strftime('%d/%m/%Y %H:%M'),
        'user': (user.get_full_name() or user.username) if user else '',
        'size': log.size_label,
        'old': format(log.old_qty.normalize(), 'f') if log.old_qty else '0',
        'new': format(log.new_qty.normalize(), 'f') if log.new_qty else '0',
        'backfill': log.is_backfill,
        'kind': log.kind,
    }


def team_day_logs(*, mo_id: int, team_slug: str) -> dict[date, list[SxTeamProgressLog]]:
    out: dict[date, list[SxTeamProgressLog]] = {}
    rows = (
        SxTeamProgressLog.objects.filter(production_order_id=mo_id, team_slug=team_slug)
        .select_related('changed_by')
        .order_by('work_date', 'changed_at', 'pk')
    )
    for log in rows:
        out.setdefault(log.work_date, []).append(log)
    return out
