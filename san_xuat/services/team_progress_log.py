"""Lịch sử sửa SL tiến độ tổ theo ngày — đánh dấu nhập bù (sửa sau ngày đó)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

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
        changed_by=user if getattr(user, 'is_authenticated', False) else None,
    )


def log_to_dict(log: SxTeamProgressLog) -> dict:
    user = log.changed_by
    return {
        'at': timezone.localtime(log.changed_at).strftime('%d/%m/%Y %H:%M'),
        'user': (user.get_full_name() or user.username) if user else '',
        'size': log.size_label,
        'old': str(log.old_qty.normalize() if log.old_qty else 0),
        'new': str(log.new_qty.normalize() if log.new_qty else 0),
        'backfill': log.is_backfill,
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
