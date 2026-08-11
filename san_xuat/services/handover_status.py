"""Tình hình bàn giao — tồn BTP giữa các tổ, lấy từ tiến độ Công việc tổ.

Không dùng phiếu bàn giao thủ công. SL tổ = thống kê SX đã xác nhận
(ghi từ phiếu tiến độ tổ). Tổ trước xong bao nhiêu thì tổ sau còn chờ bấy nhiêu.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Prefetch, Q

from san_xuat.hub_models import SxProductionOrder, SxProductionOrderLine, SxProductionStat
from san_xuat.services.order_progress_sheet import _q, _size_plans
from san_xuat.services.progress_template import (
    GROUPS,
    TEAM_SLUGS,
    ProgressStepDef,
    progress_steps,
    step_by_label,
)

# Bước đại diện lượng ra khỏi tổ. Không có thì lấy max SL các CD trong tổ.
TEAM_OUTPUT_STEP: dict[str, str | None] = {
    "CAT": None,
    "IN_EP": None,
    "THEU": None,
    "MAY": "may_giao",
    "HOAN_THANH": "ht_gap",
    "GIAO_HANG": "gh_tp",
}


@dataclass
class TeamHandoverCell:
    group_key: str
    slug: str
    label: str
    plan: Decimal
    done: Decimal
    waiting: Decimal
    incoming: Decimal
    status: str


@dataclass
class MoHandoverRow:
    mo: SxProductionOrder
    plan: Decimal
    cells: list[TeamHandoverCell]
    waiting_total: Decimal
    bottleneck: str = ""


@dataclass
class TeamQueue:
    group_key: str
    slug: str
    label: str
    waiting: Decimal
    mo_count: int


@dataclass
class HandoverBoard:
    rows: list[MoHandoverRow]
    teams: list[dict]
    queues: list[TeamQueue]
    mo_count: int = 0
    waiting_qty: Decimal = Decimal("0")
    queue_team_count: int = 0
    filter_team: str = ""
    search: str = ""


def _team_meta() -> list[dict]:
    out = []
    for slug, group_key, _menu, label in TEAM_SLUGS:
        out.append({"slug": slug, "group_key": group_key, "label": label})
    return out


def _slug_for_group(group_key: str) -> str:
    for slug, gk, _menu, _label in TEAM_SLUGS:
        if gk == group_key:
            return slug
    return ""


def _group_output(
    *,
    group_key: str,
    step_qty: dict[str, Decimal],
    group_steps: list[ProgressStepDef],
) -> Decimal:
    out_key = TEAM_OUTPUT_STEP.get(group_key)
    if out_key:
        designated = _q(step_qty.get(out_key))
        if designated > 0:
            return designated
    vals = [_q(step_qty.get(s.key)) for s in group_steps]
    return max(vals) if vals else Decimal("0")


def _cell_status(*, done: Decimal, incoming: Decimal, waiting: Decimal) -> str:
    if incoming <= 0 and done <= 0:
        return "idle"
    if incoming > 0 and done >= incoming:
        return "done"
    if done > 0:
        return "run"
    if waiting > 0:
        return "wait"
    return "idle"


def _build_row(
    mo: SxProductionOrder,
    *,
    sizes: list,
    step_size_qty: dict[tuple[str, str], Decimal],
    all_steps: list[ProgressStepDef],
) -> MoHandoverRow:
    plan = sum((r.qty for r in sizes), Decimal("0")) or _q(mo.qty)
    size_labels = [r.size_label for r in sizes] or ["Tổng"]
    size_plan = {r.size_label: r.qty for r in sizes}
    if not size_plan:
        size_plan = {"Tổng": plan}

    steps_by_group: dict[str, list[ProgressStepDef]] = {}
    for s in all_steps:
        steps_by_group.setdefault(s.group, []).append(s)

    cells: list[TeamHandoverCell] = []
    prev_output = plan
    waiting_total = Decimal("0")
    bottleneck = ""
    bottleneck_qty = Decimal("0")

    for i, grp in enumerate(GROUPS):
        g_steps = steps_by_group.get(grp.key, [])
        done = Decimal("0")
        for size in size_labels:
            step_qty = {
                s.key: _q(step_size_qty.get((size, s.key)))
                for s in g_steps
            }
            done += _group_output(group_key=grp.key, step_qty=step_qty, group_steps=g_steps)
        incoming = plan if i == 0 else prev_output
        waiting = incoming - done
        if waiting < 0:
            waiting = Decimal("0")
        if i > 0:
            waiting_total += waiting
            if waiting > bottleneck_qty:
                bottleneck_qty = waiting
                bottleneck = grp.label
        cells.append(
            TeamHandoverCell(
                group_key=grp.key,
                slug=_slug_for_group(grp.key),
                label=grp.label,
                plan=plan,
                done=done,
                waiting=waiting,
                incoming=incoming,
                status=_cell_status(done=done, incoming=incoming, waiting=waiting),
            )
        )
        prev_output = done

    return MoHandoverRow(
        mo=mo,
        plan=plan,
        cells=cells,
        waiting_total=waiting_total,
        bottleneck=bottleneck,
    )


def build_mo_handover_row(mo: SxProductionOrder) -> MoHandoverRow:
    all_steps = progress_steps()
    sizes = _size_plans(mo)
    stats = SxProductionStat.objects.filter(
        production_order=mo,
        is_demo=False,
        status=SxProductionStat.STATUS_CONFIRMED,
    ).only("process_name", "size_label", "qty_good")
    step_size_qty = _accumulate_stats(stats, sizes)
    return _build_row(mo, sizes=sizes, step_size_qty=step_size_qty, all_steps=all_steps)


def _accumulate_stats(stats, sizes) -> dict[tuple[str, str], Decimal]:
    size_set = {r.size_label for r in sizes}
    single_total = len(sizes) == 1 and sizes[0].size_label == "Tổng"
    acc: dict[tuple[str, str], Decimal] = {}
    for st in stats:
        step = step_by_label(st.process_name or "")
        if not step:
            continue
        size = (st.size_label or "").strip()
        if single_total:
            size = "Tổng"
        elif not size:
            if not size_set:
                size = "Tổng"
            else:
                continue
        qty = _q(st.qty_good)
        if qty <= 0:
            continue
        key = (size, step.key)
        acc[key] = acc.get(key, Decimal("0")) + qty
    return acc


def build_handover_board(*, search: str = "", team_slug: str = "", limit: int = 80) -> HandoverBoard:
    teams = _team_meta()
    slug = (team_slug or "").strip().lower()
    if slug and slug not in {t["slug"] for t in teams}:
        slug = ""

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

    rows: list[MoHandoverRow] = []
    for mo in mos:
        sizes = _size_plans(mo)
        acc = _accumulate_stats(stats_by_mo.get(mo.pk, []), sizes)
        rows.append(_build_row(mo, sizes=sizes, step_size_qty=acc, all_steps=all_steps))

    queues: list[TeamQueue] = []
    for t in teams:
        waiting = Decimal("0")
        n = 0
        for row in rows:
            for c in row.cells:
                if c.slug == t["slug"] and c.waiting > 0:
                    waiting += c.waiting
                    n += 1
                    break
        queues.append(TeamQueue(group_key=t["group_key"], slug=t["slug"], label=t["label"], waiting=waiting, mo_count=n))

    mid_waiting = sum((r.waiting_total for r in rows), Decimal("0"))
    queue_team_count = sum(1 for q in queues[1:] if q.waiting > 0)

    if slug:
        rows = [
            r
            for r in rows
            if any(c.slug == slug and (c.waiting > 0 or c.done > 0) for c in r.cells)
        ]
        rows.sort(
            key=lambda r: next((c.waiting for c in r.cells if c.slug == slug), Decimal("0")),
            reverse=True,
        )
    else:
        rows.sort(key=lambda r: (r.waiting_total, r.plan), reverse=True)

    return HandoverBoard(
        rows=rows,
        teams=teams,
        queues=queues,
        mo_count=len(rows),
        waiting_qty=mid_waiting,
        queue_team_count=queue_team_count,
        filter_team=slug,
        search=term,
    )
