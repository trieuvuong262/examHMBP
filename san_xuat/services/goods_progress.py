"""Tiến độ hàng hoá — timeline theo lộ trình KHSX.

Gộp mọi lệnh đang chạy, tiến độ từng tổ trên KHSX của đơn
(không ép Cắt → GH). Mỗi tổ theo dõi SL riêng — có hàng thì làm,
không chờ tổ trước. Mức độ gấp để tổ trưởng xếp việc.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal

from django.db.models import Prefetch, Q
from django.utils import timezone

from san_xuat.hub_models import (
    SxOrderTeamDayPlan,
    SxProductionOrder,
    SxProductionOrderLine,
    SxSalesOrder,
    SxSalesOrderPlanStep,
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
    product_image_url: str = ""
    product_image_urls_json: str = "[]"

    @property
    def active_labels(self) -> list[str]:
        """Tổ đang ghi SL — làm song song, không chờ tổ trước."""
        return [c.label for c in self.cells if c.status == "run"]

    @property
    def open_labels(self) -> list[str]:
        """Tổ còn SL — có hàng / còn việc thì làm."""
        return [
            c.label
            for c in self.cells
            if c.status != "skip" and c.plan > 0 and c.done < c.plan
        ]

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


def _slug_keys(slug: str) -> set[str]:
    from san_xuat.services.team_division_map import team_slug_aliases

    return {a for a in team_slug_aliases(slug) if a}


def _lookup_handover_cell(
    by_slug: dict[str, TeamHandoverCell], slug: str
) -> TeamHandoverCell | None:
    raw = (slug or "").strip().lower()
    if raw in by_slug:
        return by_slug[raw]
    for key in _slug_keys(raw):
        if key in by_slug:
            return by_slug[key]
    return None


def khsx_routes_by_order(order_ids: list[int]) -> dict[int, list[dict]]:
    """Thứ tự tổ trên KHSX từng đơn: plan_steps (sequence), bổ sung day_plans."""
    from san_xuat.services.inter_step_times import _group_slug_scope
    from san_xuat.services.plan_board import _plan_step_team_slug
    from san_xuat.services.progress_template import team_by_slug

    ids = [int(x) for x in order_ids if x]
    out: dict[int, list[dict]] = {i: [] for i in ids}
    if not ids:
        return {}

    def _stop(oid: int, slug: str, label: str, start=None, end=None, seq: int = 99) -> None:
        key = (slug or "").strip().lower()
        if not key or key == "npl":
            return
        route = out.setdefault(int(oid), [])
        for row in route:
            if row["slug"] == key:
                if start and (row["start"] is None or start < row["start"]):
                    row["start"] = start
                if end and (row["end"] is None or end > row["end"]):
                    row["end"] = end
                if label and not row["label"]:
                    row["label"] = label
                if seq < row.get("seq", 99):
                    row["seq"] = seq
                return
        meta = team_by_slug(key) or {}
        route.append({
            "slug": key,
            "label": (label or meta.get("label") or key).strip(),
            "group_key": meta.get("group_key") or "",
            "start": start,
            "end": end,
            "seq": seq,
        })

    with _group_slug_scope():
        steps = (
            SxSalesOrderPlanStep.objects.filter(sales_order_id__in=ids)
            .select_related("work_center")
            .order_by("sequence", "id")
        )
        for step in steps:
            slug = _plan_step_team_slug(step)
            wc = getattr(step, "work_center", None)
            label = ""
            if wc is not None:
                label = (wc.team_label or wc.name or wc.code or "").strip()
            planned = getattr(step, "planned_date", None)
            _stop(
                int(step.sales_order_id),
                slug,
                label,
                planned,
                planned,
                seq=int(getattr(step, "sequence", 0) or 0),
            )

    day_rows = (
        SxOrderTeamDayPlan.objects.filter(sales_order_id__in=ids)
        .select_related("work_center")
        .order_by("plan_date", "id")
    )
    for dp in day_rows:
        slug = (dp.team_slug or "").strip().lower()
        wc = getattr(dp, "work_center", None)
        label = ""
        if wc is not None:
            label = (wc.team_label or wc.name or wc.code or "").strip()
        _stop(int(dp.sales_order_id), slug, label, dp.plan_date, dp.plan_date)

    far = date(9999, 12, 31)
    for route in out.values():
        route.sort(key=lambda r: (r.get("start") or far, r.get("seq", 99), r.get("slug") or ""))
    return out


def attach_goods_product_images(rows: list[GoodsProgressRow]) -> None:
    """Gắn ảnh SP (kho / hồ sơ) lên phiếu tiến độ hàng hoá — một lần query."""
    import json

    from san_xuat.services.products import product_gallery_map

    gallery = product_gallery_map(row.mo.product_code for row in rows)
    for row in rows:
        urls = gallery.get((row.mo.product_code or "").casefold(), [])
        row.product_image_url = urls[0] if urls else ""
        row.product_image_urls_json = json.dumps(urls, ensure_ascii=False)


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


def _align_cells_to_khsx(
    cells: list[TeamHandoverCell],
    route: list[dict] | None,
    *,
    teams: list[dict],
    plan: Decimal,
) -> list[TeamHandoverCell]:
    """Timeline = tổ trên KHSX của đơn; không có lộ trình thì giữ mẫu cố định."""
    if not route:
        return _align_cells(cells, teams)
    by_slug = {c.slug: c for c in cells}
    aligned: list[TeamHandoverCell] = []
    for stop in route:
        slug = (stop.get("slug") or "").strip().lower()
        if not slug:
            continue
        src = _lookup_handover_cell(by_slug, slug)
        label = (stop.get("label") or (src.label if src else "") or slug).strip()
        if src:
            aligned.append(
                replace(
                    src,
                    slug=slug,
                    label=label,
                    khsx_start=stop.get("start") or src.khsx_start,
                    khsx_end=stop.get("end") or src.khsx_end,
                )
            )
            continue
        qty = plan if plan > 0 else Decimal("0")
        aligned.append(
            TeamHandoverCell(
                group_key=stop.get("group_key") or "",
                slug=slug,
                label=label,
                plan=qty,
                done=Decimal("0"),
                waiting=qty,
                incoming=qty,
                status="idle" if qty > 0 else "skip",
                khsx_start=stop.get("start"),
                khsx_end=stop.get("end"),
            )
        )
    return aligned


def _enrich_row(
    handover,
    *,
    today: date,
    teams: list[dict],
    route: list[dict] | None = None,
) -> GoodsProgressRow:
    mo = handover.mo
    due = _due_for(mo)
    days = (due - today).days if due else None
    overdue = bool(due and days is not None and days < 0 and mo.status != SxProductionOrder.STATUS_DONE)
    priority = _priority_for(mo)
    is_hot = overdue or priority in (
        SxSalesOrder.PRIORITY_CRITICAL,
        SxSalesOrder.PRIORITY_URGENT,
    )
    cells = _align_cells_to_khsx(
        handover.cells, route, teams=teams, plan=handover.plan
    )
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
        ctx = None
        if slug:
            for key in (slug, *_slug_keys(slug)):
                ctx = ctx_map.get((row.so_id, key))
                if ctx is not None:
                    break
        if ctx is None:
            continue
        row.khsx_start = ctx.start
        row.khsx_end = ctx.end
        row.khsx_team_label = ctx.work_center_label or row.current_team
        unfinished = row.status != SxProductionOrder.STATUS_DONE
        row.khsx_is_late = bool(
            unfinished
            and any(
                c.khsx_end
                and today > c.khsx_end
                and c.status != "skip"
                and c.plan > 0
                and c.done < c.plan
                for c in row.cells
            )
            or (
                unfinished
                and ctx.end
                and today > ctx.end
                and any(c.plan > 0 and c.done < c.plan for c in row.cells)
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


def _build_khsx_queues(rows: list[GoodsProgressRow]) -> list[TeamQueue]:
    """Thanh pipeline = các tổ thật sự có trên KHSX, không lấy 6 tổ mẫu."""
    from san_xuat.services.progress_template import team_by_slug
    from san_xuat.services.team_division_map import khsx_slug_for_team

    seen: dict[str, str] = {}
    group_of: dict[str, str] = {}
    for row in rows:
        for cell in row.cells:
            slug = (cell.slug or "").strip().lower()
            if not slug or (cell.status == "skip" and not cell.plan and not cell.done):
                continue
            if slug not in seen:
                seen[slug] = cell.label
                meta = team_by_slug(slug) or {}
                group_of[slug] = meta.get("group_key") or ""
    if not seen:
        return []
    rank = {slug: idx for idx, (slug, *_rest) in enumerate(TEAM_SLUGS)}

    def _rk(slug: str) -> tuple:
        stage = khsx_slug_for_team(team_by_slug(slug), slug)
        return (rank.get(stage, rank.get(slug, 50)), slug)

    queues: list[TeamQueue] = []
    for slug in sorted(seen, key=_rk):
        keys = _slug_keys(slug) | {slug}
        active = sum(
            1
            for r in rows
            if r.status != SxProductionOrder.STATUS_DONE
            and any(
                (c.slug in keys or bool(_slug_keys(c.slug) & keys))
                and c.status != "skip"
                and c.plan > 0
                and c.done < c.plan
                for c in r.cells
            )
        )
        waiting = Decimal("0")
        for r in rows:
            for c in r.cells:
                if (c.slug in keys or bool(_slug_keys(c.slug) & keys)) and c.waiting > 0:
                    waiting += c.waiting
                    break
        queues.append(
            TeamQueue(
                group_key=group_of.get(slug, ""),
                slug=slug,
                label=seen[slug],
                waiting=waiting,
                mo_count=active,
            )
        )
    return queues


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
        keys = _slug_keys(team_key) | {team_key}
        filtered = [
            r
            for r in filtered
            if any(
                (c.slug in keys or bool(_slug_keys(c.slug) & keys))
                and c.status != "skip"
                and (c.plan > 0 or c.done > 0)
                for c in r.cells
            )
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
            Prefetch(
                "sales_order__plan_steps",
                queryset=SxSalesOrderPlanStep.objects.select_related("work_center").order_by(
                    "sequence", "id"
                ),
            ),
            Prefetch(
                "sales_order__team_day_plans",
                queryset=SxOrderTeamDayPlan.objects.select_related("work_center").order_by(
                    "plan_date", "id"
                ),
            ),
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
    routes = khsx_routes_by_order([int(m.sales_order_id or 0) for m in mos])
    rows: list[GoodsProgressRow] = [
        _enrich_row(
            h,
            today=today,
            teams=teams,
            route=routes.get(int(h.mo.sales_order_id or 0)) or None,
        )
        for h in handovers
    ]
    attach_goods_product_images(rows)

    team_key = (team_slug or "").strip().lower()
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

    queues = _build_khsx_queues(rows)
    team_choices = [(q.slug, q.label) for q in queues] or [
        (slug, label) for slug, _gk, _mk, label in TEAM_SLUGS
    ]

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
