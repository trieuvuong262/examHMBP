"""Tiến độ hàng hoá — bảng tổng cho tổ trưởng.

Gộp mọi lệnh đang chạy, tiến độ từng tổ (Cắt → GH) và mức độ gấp
(đơn hàng + hạn giao) để tổ tự sắp xếp công nhân.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import Prefetch, Q
from django.utils import timezone

from san_xuat.hub_models import (
    SxProductionOrder,
    SxProductionOrderLine,
    SxProductionStat,
    SxSalesOrder,
)
from san_xuat.services.handover_status import (
    TeamHandoverCell,
    TeamQueue,
    _accumulate_stats,
    _build_row,
    _team_meta,
)
from san_xuat.services.order_progress_sheet import _q, _size_plans
from san_xuat.services.progress_template import progress_steps

PRIORITY_RANK = {
    SxSalesOrder.PRIORITY_CRITICAL: 0,
    SxSalesOrder.PRIORITY_URGENT: 1,
    SxSalesOrder.PRIORITY_HIGH: 2,
    SxSalesOrder.PRIORITY_NORMAL: 3,
    SxSalesOrder.PRIORITY_LOW: 4,
}
PRIORITY_LABEL = dict(SxSalesOrder.PRIORITY_CHOICES)
_FAR = date(9999, 12, 31)


@dataclass
class GoodsProgressRow:
    mo: SxProductionOrder
    plan: Decimal
    cells: list[TeamHandoverCell]
    waiting_total: Decimal
    bottleneck: str
    priority: str
    priority_label: str
    due: date | None
    days_to_due: int | None
    is_overdue: bool
    is_hot: bool
    current_team: str
    current_slug: str
    status: str
    status_label: str

    @property
    def due_label(self) -> str:
        if self.days_to_due is None:
            return ""
        if self.status == SxProductionOrder.STATUS_DONE:
            return "Đã xong"
        n = self.days_to_due
        if n < 0:
            return f"Trễ {abs(n)} ngày"
        if n == 0:
            return "Hạn hôm nay"
        if n == 1:
            return "Còn 1 ngày"
        return f"Còn {n} ngày"

    @property
    def progress_pct(self) -> int:
        if not self.cells or self.plan <= 0:
            return 0
        last = self.cells[-1]
        pct = int((_q(last.done) / _q(self.plan)) * 100)
        return min(100, max(0, pct))

    @property
    def sort_key(self) -> tuple:
        return (
            0 if self.is_overdue else 1,
            PRIORITY_RANK.get(self.priority, 3),
            self.due or _FAR,
            0 if self.status != SxProductionOrder.STATUS_DONE else 1,
            -self.waiting_total,
            self.mo.code or "",
        )


@dataclass
class GoodsProgressBoard:
    rows: list[GoodsProgressRow]
    mo_count: int = 0
    hot_count: int = 0
    overdue_count: int = 0
    running_count: int = 0
    not_started_count: int = 0
    almost_done_count: int = 0
    done_count: int = 0
    search: str = ""
    filter_key: str = ""
    filter_team: str = ""
    filter_priority: str = ""
    filter_status: str = ""
    filter_due: str = ""
    filter_progress: str = ""
    has_filters: bool = False
    queues: list[TeamQueue] | None = None


def _due_for(mo: SxProductionOrder) -> date | None:
    so = mo.sales_order if mo.sales_order_id else None
    return mo.due_date or mo.planned_end or (so.due_date if so else None)


def _priority_for(mo: SxProductionOrder) -> str:
    so = mo.sales_order if mo.sales_order_id else None
    raw = (so.plan_priority if so else "") or SxSalesOrder.PRIORITY_NORMAL
    return raw if raw in PRIORITY_RANK else SxSalesOrder.PRIORITY_NORMAL


def _current_team(cells: list[TeamHandoverCell]) -> tuple[str, str]:
    for c in cells:
        if c.status == "run":
            return c.label, c.slug
    for c in cells:
        if c.done < c.plan:
            return c.label, c.slug
    if cells:
        last = cells[-1]
        return last.label, last.slug
    return "", ""


def _enrich_row(handover, *, today: date) -> GoodsProgressRow:
    mo = handover.mo
    due = _due_for(mo)
    days = (due - today).days if due else None
    overdue = bool(due and days is not None and days < 0 and mo.status != SxProductionOrder.STATUS_DONE)
    priority = _priority_for(mo)
    is_hot = overdue or priority in (
        SxSalesOrder.PRIORITY_CRITICAL,
        SxSalesOrder.PRIORITY_URGENT,
    )
    current_label, current_slug = _current_team(handover.cells)
    return GoodsProgressRow(
        mo=mo,
        plan=handover.plan,
        cells=handover.cells,
        waiting_total=handover.waiting_total,
        bottleneck=handover.bottleneck,
        priority=priority,
        priority_label=PRIORITY_LABEL.get(priority, "Thường"),
        due=due,
        days_to_due=days,
        is_overdue=overdue,
        is_hot=is_hot,
        current_team=current_label,
        current_slug=current_slug,
        status=mo.status,
        status_label=mo.get_status_display(),
    )


def _matches_team_filter(row: GoodsProgressRow, slug: str) -> bool:
    return any(
        c.slug == slug and (c.done > 0 or c.done < c.plan)
        for c in row.cells
    )


def _matches_due_filter(row: GoodsProgressRow, due_key: str) -> bool:
    if due_key == "overdue":
        return row.is_overdue
    if due_key == "today":
        return row.days_to_due == 0 and row.status != SxProductionOrder.STATUS_DONE
    if due_key == "week":
        return (
            row.days_to_due is not None
            and 0 <= row.days_to_due <= 7
            and row.status != SxProductionOrder.STATUS_DONE
        )
    if due_key == "none":
        return row.due is None
    return True


def _matches_progress_filter(row: GoodsProgressRow, progress_key: str) -> bool:
    pct = row.progress_pct
    if progress_key == "zero":
        return pct == 0
    if progress_key == "partial":
        return 0 < pct < 100
    if progress_key == "complete":
        return pct >= 100
    return True


def _apply_row_filters(
    rows: list[GoodsProgressRow],
    *,
    filter_key: str,
    team_slug: str,
    priority: str,
    mo_status: str,
    due_key: str,
    progress_key: str,
) -> list[GoodsProgressRow]:
    filtered = rows
    fkey = (filter_key or "").strip().lower()
    if fkey == "hot":
        filtered = [r for r in filtered if r.is_hot]
    elif fkey == "overdue":
        filtered = [r for r in filtered if r.is_overdue]
    elif fkey == "running":
        filtered = [
            r
            for r in filtered
            if r.status
            in (SxProductionOrder.STATUS_RELEASED, SxProductionOrder.STATUS_IN_PROGRESS)
        ]
    elif fkey == "not_started":
        filtered = [
            r
            for r in filtered
            if r.progress_pct == 0 and r.status != SxProductionOrder.STATUS_DONE
        ]
    elif fkey == "almost_done":
        filtered = [r for r in filtered if 80 <= r.progress_pct < 100]

    team_filter = (team_slug or "").strip().lower()
    if team_filter:
        filtered = [r for r in filtered if _matches_team_filter(r, team_filter)]

    priority_key = (priority or "").strip().lower()
    if priority_key and priority_key in PRIORITY_RANK:
        filtered = [r for r in filtered if r.priority == priority_key]

    status_key = (mo_status or "").strip().lower()
    if status_key in (
        SxProductionOrder.STATUS_RELEASED,
        SxProductionOrder.STATUS_IN_PROGRESS,
        SxProductionOrder.STATUS_DONE,
    ):
        filtered = [r for r in filtered if r.status == status_key]

    due_filter = (due_key or "").strip().lower()
    if due_filter in ("overdue", "today", "week", "none"):
        filtered = [r for r in filtered if _matches_due_filter(r, due_filter)]

    progress_filter = (progress_key or "").strip().lower()
    if progress_filter in ("zero", "partial", "complete"):
        filtered = [r for r in filtered if _matches_progress_filter(r, progress_filter)]

    if team_filter:
        filtered.sort(
            key=lambda r: (
                0 if r.current_slug == team_filter else 1,
                r.sort_key,
            )
        )
    else:
        filtered.sort(key=lambda r: r.sort_key)
    return filtered


def build_goods_progress_board(
    *,
    search: str = "",
    filter_key: str = "",
    team_slug: str = "",
    priority: str = "",
    mo_status: str = "",
    due: str = "",
    progress: str = "",
    today: date | None = None,
    limit: int = 150,
) -> GoodsProgressBoard:
    today = today or timezone.localdate()

    qs = (
        SxProductionOrder.objects.filter(is_demo=False)
        .exclude(status=SxProductionOrder.STATUS_CANCELLED)
        .exclude(status=SxProductionOrder.STATUS_DRAFT)
        .select_related("sales_order")
        .prefetch_related(
            Prefetch(
                "lines",
                queryset=SxProductionOrderLine.objects.order_by("size_label", "id"),
            ),
            "mo_process_steps",
        )
        .order_by("-order_date", "-pk")
    )
    term = (search or "").strip()
    if term:
        qs = qs.filter(
            Q(code__icontains=term)
            | Q(product_code__icontains=term)
            | Q(product_name__icontains=term)
            | Q(sales_order__code__icontains=term)
        )

    mos = list(qs[:limit])
    all_steps = progress_steps()
    stats_by_mo: dict[int, list[SxProductionStat]] = {mo.pk: [] for mo in mos}
    if mos:
        for st in SxProductionStat.objects.filter(
            production_order_id__in=[m.pk for m in mos],
            is_demo=False,
            status=SxProductionStat.STATUS_CONFIRMED,
        ).only("production_order_id", "process_name", "size_label", "qty_good"):
            stats_by_mo.setdefault(st.production_order_id, []).append(st)

    rows: list[GoodsProgressRow] = []
    for mo in mos:
        sizes = _size_plans(mo)
        acc = _accumulate_stats(stats_by_mo.get(mo.pk, []), sizes)
        handover = _build_row(mo, sizes=sizes, step_size_qty=acc, all_steps=all_steps)
        rows.append(_enrich_row(handover, today=today))

    hot_count = sum(1 for r in rows if r.is_hot)
    overdue_count = sum(1 for r in rows if r.is_overdue)
    running_count = sum(
        1
        for r in rows
        if r.status in (SxProductionOrder.STATUS_RELEASED, SxProductionOrder.STATUS_IN_PROGRESS)
    )
    not_started_count = sum(
        1
        for r in rows
        if r.progress_pct == 0 and r.status != SxProductionOrder.STATUS_DONE
    )
    almost_done_count = sum(1 for r in rows if 80 <= r.progress_pct < 100)
    done_count = sum(1 for r in rows if r.status == SxProductionOrder.STATUS_DONE)

    teams = _team_meta()
    team_filter = (team_slug or "").strip().lower()
    if team_filter and team_filter not in {t["slug"] for t in teams}:
        team_filter = ""

    queues: list[TeamQueue] = []
    for t in teams:
        active = sum(
            1
            for r in rows
            if r.current_slug == t["slug"]
            and r.status != SxProductionOrder.STATUS_DONE
        )
        waiting = Decimal("0")
        for r in rows:
            for c in r.cells:
                if c.slug == t["slug"] and c.waiting > 0:
                    waiting += c.waiting
                    break
        queues.append(
            TeamQueue(
                group_key=t["group_key"],
                slug=t["slug"],
                label=t["label"],
                waiting=waiting,
                mo_count=active,
            )
        )

    fkey = (filter_key or "").strip().lower()
    if fkey not in ("", "hot", "overdue", "running", "not_started", "almost_done"):
        fkey = ""

    priority_key = (priority or "").strip().lower()
    if priority_key and priority_key not in PRIORITY_RANK:
        priority_key = ""

    status_key = (mo_status or "").strip().lower()
    if status_key not in (
        "",
        SxProductionOrder.STATUS_RELEASED,
        SxProductionOrder.STATUS_IN_PROGRESS,
        SxProductionOrder.STATUS_DONE,
    ):
        status_key = ""

    due_filter = (due or "").strip().lower()
    if due_filter not in ("", "overdue", "today", "week", "none"):
        due_filter = ""

    progress_filter = (progress or "").strip().lower()
    if progress_filter not in ("", "zero", "partial", "complete"):
        progress_filter = ""

    filtered = _apply_row_filters(
        rows,
        filter_key=fkey,
        team_slug=team_filter,
        priority=priority_key,
        mo_status=status_key,
        due_key=due_filter,
        progress_key=progress_filter,
    )

    has_filters = bool(
        term
        or fkey
        or team_filter
        or priority_key
        or status_key
        or due_filter
        or progress_filter
    )

    return GoodsProgressBoard(
        rows=filtered,
        mo_count=len(rows),
        hot_count=hot_count,
        overdue_count=overdue_count,
        running_count=running_count,
        not_started_count=not_started_count,
        almost_done_count=almost_done_count,
        done_count=done_count,
        search=term,
        filter_key=fkey,
        filter_team=team_filter,
        filter_priority=priority_key,
        filter_status=status_key,
        filter_due=due_filter,
        filter_progress=progress_filter,
        has_filters=has_filters,
        queues=queues,
    )
