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


@transaction.atomic
def fill_remaining_on_complete(*, mo: SxProductionOrder, team_meta: dict, team_slug: str, user) -> Decimal:
    """Khi tổ bấm Hoàn thành: bù phần còn thiếu của từng size × công đoạn vào hôm nay.

    SL đã nhập giữ nguyên; công đoạn đã đủ / vượt kế hoạch không đổi. Trả về
    tổng SL tổ (theo bộ) được điền thêm.
    """
    from san_xuat.services.dispatch import _recompute_mo_progress
    from san_xuat.services.order_progress_sheet import (
        build_progress_sheet,
        progress_steps_for_team,
        record_progress_qty,
        team_day_qty,
    )

    steps = progress_steps_for_team(mo, team_meta)
    if not steps:
        return Decimal('0')
    sheet = build_progress_sheet(mo, team=team_meta)
    if not sheet.sizes:
        return Decimal('0')
    today = timezone.localdate()
    zero = Decimal('0')
    before = team_day_qty(sheet, steps=steps, day=today)
    team_before = {r['size_label']: r['total_done'] for r in sheet.done_rows}

    wrote = False
    for row in sheet.sizes:
        if row.qty <= 0:
            continue
        cells = sheet.matrix.get(row.size_label, {})
        for step in steps:
            done = cells[step.key].done if step.key in cells else zero
            missing = row.qty - done
            if missing > 0:
                record_progress_qty(
                    mo_id=mo.pk,
                    process_key=step.key,
                    size_label=row.size_label,
                    qty=missing,
                    stat_date=today,
                    user=user,
                    team_slug=team_slug,
                    recompute=False,
                )
                wrote = True
    if not wrote:
        return zero
    _recompute_mo_progress(SxProductionOrder.objects.get(pk=mo.pk))

    sheet = build_progress_sheet(mo, team=team_meta)
    after = team_day_qty(sheet, steps=steps, day=today)
    filled = zero
    for r in sheet.done_rows:
        size = r['size_label']
        filled += max(r['total_done'] - team_before.get(size, zero), zero)
        log_day_change(
            mo=mo,
            team_slug=team_slug,
            work_date=today,
            size_label=size,
            old_qty=before.get(size, zero),
            new_qty=after.get(size, zero),
            user=user,
            kind=SxTeamProgressLog.KIND_COMPLETE,
        )
    return filled


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
