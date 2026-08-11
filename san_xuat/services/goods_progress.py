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
    SxProductionStat,
    SxSalesOrder,
)
from san_xuat.services.handover_status import (
    TeamHandoverCell,
    _accumulate_stats,
    _build_row,
    _team_meta,
)
from san_xuat.services.order_progress_sheet import _size_plans
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
    teams: list[dict]
    mo_count: int = 0
    hot_count: int = 0
    overdue_count: int = 0
    running_count: int = 0
    search: str = ""
    filter_kind: str = ""
    filter_team: str = ""
    kinds: list[dict] = field(default_factory=list)


def _due_for(mo: SxProductionOrder) -> date | None:
    so = mo.sales_order if mo.sales_order_id else None
    return mo.due_date or mo.planned_end or (so.due_date if so else None)


def _priority_for(mo: SxProductionOrder) -> str:
    so = mo.sales_order if mo.sales_order_id else None
    raw = (so.plan_priority if so else "") or SxSalesOrder.PRIORITY_NORMAL
    return raw if raw in PRIORITY_RANK else SxSalesOrder.PRIORITY_NORMAL


def _current_team(cells: list[TeamHandoverCell]) -> tuple[str, str]:
    for c in cells:
        if c.status in ("wait", "run"):
            return c.label, c.slug
    if cells and all(c.status == "done" for c in cells):
        last = cells[-1]
        return last.label, last.slug
    if cells:
        return cells[0].label, cells[0].slug
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


def build_goods_progress_board(
    *,
    search: str = "",
    kind: str = "",
    team_slug: str = "",
    today: date | None = None,
    limit: int = 150,
) -> GoodsProgressBoard:
    today = today or timezone.localdate()
    teams = _team_meta()
    slug = (team_slug or "").strip().lower()
    if slug and slug not in {t["slug"] for t in teams}:
        slug = ""
    kind = (kind or "").strip().lower()
    if kind not in ("hot", "late", "run"):
        kind = ""

    qs = (
        SxProductionOrder.objects.filter(is_demo=False)
        .exclude(status=SxProductionOrder.STATUS_CANCELLED)
        .exclude(status=SxProductionOrder.STATUS_DRAFT)
        .select_related("sales_order")
        .prefetch_related(
            Prefetch(
                "lines",
                queryset=SxProductionOrderLine.objects.order_by("size_label", "id"),
            )
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

    filtered = rows
    if kind == "hot":
        filtered = [r for r in filtered if r.is_hot]
    elif kind == "late":
        filtered = [r for r in filtered if r.is_overdue]
    elif kind == "run":
        filtered = [
            r
            for r in filtered
            if r.status in (SxProductionOrder.STATUS_RELEASED, SxProductionOrder.STATUS_IN_PROGRESS)
        ]
    if slug:
        filtered = [
            r
            for r in filtered
            if any(c.slug == slug and c.status in ("wait", "run") for c in r.cells)
        ]

    filtered.sort(key=lambda r: r.sort_key)

    return GoodsProgressBoard(
        rows=filtered,
        teams=teams,
        mo_count=len(rows),
        hot_count=hot_count,
        overdue_count=overdue_count,
        running_count=running_count,
        search=term,
        filter_kind=kind,
        filter_team=slug,
        kinds=[
            {"key": "", "label": "Tất cả", "count": len(rows)},
            {"key": "hot", "label": "Gấp", "count": hot_count},
            {"key": "late", "label": "Trễ hạn", "count": overdue_count},
            {"key": "run", "label": "Đang SX", "count": running_count},
        ],
    )
