"""Tiến độ hàng hoá — bảng tổng cho tổ trưởng.

Gộp mọi lệnh đang chạy, tiến độ từng tổ (Cắt → GH) và mức độ gấp
(đơn hàng + hạn giao) để tổ tự sắp xếp công nhân.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.db.models import Prefetch, Q
from django.utils import timezone

from san_xuat.hub_models import (
    SxProductionOrder,
    SxProductionOrderLine,
    SxSalesOrder,
)
from san_xuat.services.handover_status import (
    TeamHandoverCell,
    TeamQueue,
    _team_meta,
    attach_gc_to_handover_rows,
    attach_qc_to_handover_rows,
    build_mo_handover_rows,
    khsx_context_by_order_team,
)
from san_xuat.services.order_progress_sheet import _q
from san_xuat.services.progress_template import TEAM_SLUGS

PRIORITY_RANK = {
    SxSalesOrder.PRIORITY_CRITICAL: 0,
    SxSalesOrder.PRIORITY_URGENT: 1,
    SxSalesOrder.PRIORITY_HIGH: 2,
    SxSalesOrder.PRIORITY_NORMAL: 3,
    SxSalesOrder.PRIORITY_LOW: 4,
}
PRIORITY_LABEL = dict(SxSalesOrder.PRIORITY_CHOICES)
_FAR = date(9999, 12, 31)
CLUSTER_SORTS = ("", "urgent", "due", "priority")


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
    so_id: int = 0
    so_code: str = ""
    is_so_start: bool = False
    plan_status_label: str = ""
    khsx_start: date | None = None
    khsx_end: date | None = None
    khsx_team_label: str = ""
    khsx_is_late: bool = False

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
        planned = _q(self.mo.qty) or _q(self.plan)
        if planned <= 0:
            return 0
        pct = int((_q(self.mo.qty_done) / planned) * 100)
        return min(100, max(0, pct))

    @property
    def sort_key(self) -> tuple:
        return (
            0 if self.is_overdue else 1,
            PRIORITY_RANK.get(self.priority, 3),
            self.due or _FAR,
            0 if self.status != SxProductionOrder.STATUS_DONE else 1,
            self.so_id or 0,
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
    filter_priority: str = ""
    filter_status: str = ""
    filter_due: str = ""
    filter_team: str = ""
    sort: str = ""
    has_filters: bool = False
    queues: list[TeamQueue] | None = None
    team_choices: list[tuple[str, str]] = field(default_factory=list)


def _due_for(mo: SxProductionOrder) -> date | None:
    """Hạn giao trên KHSX (ưu tiên hạn đơn hàng)."""
    so = mo.sales_order if mo.sales_order_id else None
    return (so.due_date if so else None) or mo.due_date or mo.planned_end


def _priority_for(mo: SxProductionOrder) -> str:
    so = mo.sales_order if mo.sales_order_id else None
    raw = (so.plan_priority if so else "") or SxSalesOrder.PRIORITY_NORMAL
    return raw if raw in PRIORITY_RANK else SxSalesOrder.PRIORITY_NORMAL


def _current_team(cells: list[TeamHandoverCell]) -> tuple[str, str]:
    for c in cells:
        if c.status == "run":
            return c.label, c.slug
    for c in cells:
        if c.status != "skip" and c.plan > 0 and c.done < c.plan:
            return c.label, c.slug
    for c in reversed(cells):
        if c.status != "skip" and c.plan > 0:
            return c.label, c.slug
    return "", ""


def _align_cells(cells: list[TeamHandoverCell], teams: list[dict]) -> list[TeamHandoverCell]:
    by_slug = {c.slug: c for c in cells}
    aligned: list[TeamHandoverCell] = []
    for t in teams:
        cell = by_slug.get(t["slug"])
        if cell:
            aligned.append(cell)
            continue
        aligned.append(
            TeamHandoverCell(
                group_key=t["group_key"],
                slug=t["slug"],
                label=t["label"],
                plan=Decimal("0"),
                done=Decimal("0"),
                waiting=Decimal("0"),
                incoming=Decimal("0"),
                status="skip",
            )
        )
    return aligned


def _enrich_row(handover, *, today: date, teams: list[dict]) -> GoodsProgressRow:
    mo = handover.mo
    due = _due_for(mo)
    days = (due - today).days if due else None
    overdue = bool(due and days is not None and days < 0 and mo.status != SxProductionOrder.STATUS_DONE)
    priority = _priority_for(mo)
    is_hot = overdue or priority in (
        SxSalesOrder.PRIORITY_CRITICAL,
        SxSalesOrder.PRIORITY_URGENT,
    )
    cells = _align_cells(handover.cells, teams)
    current_label, current_slug = _current_team(cells)
    so = mo.sales_order if mo.sales_order_id else None
    plan_status_label = ""
    if so is not None:
        plan_status_label = so.get_plan_status_display() or ""
    return GoodsProgressRow(
        mo=mo,
        plan=handover.plan,
        cells=cells,
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
        so_id=int(mo.sales_order_id or 0),
        so_code=(so.code if so else "") or "",
        plan_status_label=plan_status_label,
    )


def _attach_khsx(rows: list[GoodsProgressRow], *, today: date, team_filter: str) -> None:
    order_ids = [r.so_id for r in rows if r.so_id]
    if not order_ids:
        return
    ctx_map = khsx_context_by_order_team(order_ids)
    for row in rows:
        slug = (team_filter or row.current_slug or "").strip().lower()
        ctx = ctx_map.get((row.so_id, slug)) if slug else None
        if ctx is None:
            continue
        row.khsx_start = ctx.start
        row.khsx_end = ctx.end
        row.khsx_team_label = ctx.work_center_label or row.current_team
        unfinished = row.status != SxProductionOrder.STATUS_DONE
        row.khsx_is_late = bool(
            unfinished and ctx.end and today > ctx.end and any(
                c.slug == slug and c.plan > 0 and c.done < c.plan for c in row.cells
            )
        )


def _mark_so_groups(rows: list[GoodsProgressRow], *, sort_key: str) -> None:
    if sort_key not in CLUSTER_SORTS:
        return
    prev = None
    for row in rows:
        sid = row.so_id or None
        row.is_so_start = bool(sid) and sid != prev
        prev = sid


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


def _apply_row_filters(
    rows: list[GoodsProgressRow],
    *,
    priority: str,
    mo_status: str,
    due_key: str,
    team_slug: str,
) -> list[GoodsProgressRow]:
    filtered = rows

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

    team_key = (team_slug or "").strip().lower()
    if team_key:
        filtered = [
            r
            for r in filtered
            if any(c.slug == team_key and c.status != "skip" and c.plan > 0 for c in r.cells)
        ]

    return filtered


SORT_KEYS = (
    "",
    "urgent",
    "due",
    "priority",
    "progress_asc",
    "progress_desc",
    "qty",
    "name",
    "code",
)


def _sort_rows(
    rows: list[GoodsProgressRow],
    *,
    sort_key: str,
) -> list[GoodsProgressRow]:
    key = (sort_key or "").strip().lower()
    if key not in SORT_KEYS:
        key = ""

    def _by(row: GoodsProgressRow):
        if key == "due":
            base = (row.due or _FAR, row.so_id or 0, row.mo.code or "")
        elif key == "priority":
            base = (
                PRIORITY_RANK.get(row.priority, 3),
                row.due or _FAR,
                row.so_id or 0,
                row.mo.code or "",
            )
        elif key == "progress_asc":
            base = (row.progress_pct, row.mo.code or "")
        elif key == "progress_desc":
            base = (-row.progress_pct, row.mo.code or "")
        elif key == "qty":
            base = (-row.plan, row.mo.code or "")
        elif key == "name":
            name = (row.mo.product_name or row.mo.product_code or "").casefold()
            base = (name, row.mo.code or "")
        elif key == "code":
            base = (row.mo.code or "",)
        else:
            base = row.sort_key
        return base

    rows.sort(key=_by)
    return rows


def build_goods_progress_board(
    *,
    search: str = "",
    priority: str = "",
    mo_status: str = "",
    due: str = "",
    sort: str = "",
    team_slug: str = "",
    today: date | None = None,
    limit: int | None = None,
) -> GoodsProgressBoard:
    today = today or timezone.localdate()
    teams = _team_meta()
    team_choices = [(slug, label) for slug, _gk, _mk, label in TEAM_SLUGS]

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
            "sales_order__lines__routing_lines__work_center",
            "routing__lines__work_center",
            "bom_version__process_steps__work_center",
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

    mos = list(qs[:limit] if limit else qs)
    handovers = build_mo_handover_rows(mos)
    attach_qc_to_handover_rows(handovers)
    attach_gc_to_handover_rows(handovers)
    rows: list[GoodsProgressRow] = [
        _enrich_row(h, today=today, teams=teams) for h in handovers
    ]

    team_key = (team_slug or "").strip().lower()
    if team_key and team_key not in {t["slug"] for t in teams}:
        team_key = ""
    _attach_khsx(rows, today=today, team_filter=team_key)

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

    sort_key = (sort or "").strip().lower()
    if sort_key not in SORT_KEYS:
        sort_key = ""

    filtered = _apply_row_filters(
        rows,
        priority=priority_key,
        mo_status=status_key,
        due_key=due_filter,
        team_slug=team_key,
    )
    filtered = _sort_rows(filtered, sort_key=sort_key)
    _mark_so_groups(filtered, sort_key=sort_key)

    has_filters = bool(
        term
        or priority_key
        or status_key
        or due_filter
        or team_key
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
        filter_priority=priority_key,
        filter_status=status_key,
        filter_due=due_filter,
        filter_team=team_key,
        sort=sort_key,
        has_filters=has_filters,
        queues=queues,
        team_choices=team_choices,
    )
