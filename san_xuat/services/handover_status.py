"""Tình hình tiến độ theo tổ — SL đạt so với kế hoạch lệnh.

Lấy từ thống kê SX đã xác nhận (ghi từ phiếu tiến độ tổ). Mỗi tổ theo dõi
độc lập so với SL lệnh; không bắt buộc hoàn thành tổ trước mới làm tổ sau.
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

# Bước đại diện lượng ra khỏi tổ. Không có thì lấy min SL các CD của tổ trên lệnh
# (áo/quần/phối cắt đủ mới tính 1 bộ — không lấy max một CD).
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
    qc_status: str = "skip"
    qc_required: bool = False
    qc_inspection_id: int | None = None
    subcontract: object | None = None

    @property
    def qc_status_label(self) -> str:
        from san_xuat.services.qc import QC_STATUS_LABELS

        return QC_STATUS_LABELS.get(self.qc_status, self.qc_status)

    @property
    def qc_progress_done(self) -> bool:
        from san_xuat.services.qc import QC_PROGRESS_DONE

        return self.qc_status in QC_PROGRESS_DONE

    @property
    def qc_progress_label(self) -> str:
        if not self.qc_required or self.qc_status == "skip":
            return "—"
        return "Đã kiểm" if self.qc_progress_done else "Chưa kiểm"

    @property
    def qc_progress_kind(self) -> str:
        if not self.qc_required or self.qc_status == "skip":
            return "skip"
        return "checked" if self.qc_progress_done else "pending"


@dataclass
class MoHandoverRow:
    mo: SxProductionOrder
    plan: Decimal
    cells: list[TeamHandoverCell]
    waiting_total: Decimal
    bottleneck: str = ""
    qc_inspection_id: int | None = None


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


def _required_step_keys(mo: SxProductionOrder, group_key: str) -> set[str]:
    keys: set[str] = set()
    rel = getattr(mo, "mo_process_steps", None)
    if rel is None:
        return keys
    try:
        steps = rel.all()
    except Exception:
        steps = rel
    for ps in steps:
        sd = step_by_label(getattr(ps, "process_name", "") or "")
        if sd and sd.group == group_key:
            keys.add(sd.key)
    return keys


def _group_output(
    *,
    group_key: str,
    step_qty: dict[str, Decimal],
    group_steps: list[ProgressStepDef],
    required_keys: set[str] | None = None,
) -> Decimal:
    out_key = TEAM_OUTPUT_STEP.get(group_key)
    if out_key:
        designated = _q(step_qty.get(out_key))
        if designated > 0:
            return designated
    keys = [s.key for s in group_steps]
    if required_keys:
        need = [k for k in keys if k in required_keys]
        if need:
            return min(_q(step_qty.get(k)) for k in need)
    recorded = [_q(step_qty.get(s.key)) for s in group_steps if _q(step_qty.get(s.key)) > 0]
    if not recorded:
        return Decimal("0")
    return min(recorded)


def _cell_status(*, done: Decimal, plan: Decimal) -> str:
    if done <= 0:
        return "idle"
    if done >= plan:
        return "done"
    return "run"


def _build_row(
    mo: SxProductionOrder,
    *,
    sizes: list,
    step_size_qty: dict[tuple[str, str], Decimal],
    all_steps: list[ProgressStepDef],
    participating_slugs: set[str] | None = None,
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
    waiting_total = Decimal("0")
    bottleneck = ""
    bottleneck_qty = Decimal("0")

    for grp in GROUPS:
        slug = _slug_for_group(grp.key)
        if participating_slugs is not None and slug not in participating_slugs:
            continue
        g_steps = steps_by_group.get(grp.key, [])
        required = _required_step_keys(mo, grp.key)
        done = Decimal("0")
        for size in size_labels:
            step_qty = {
                s.key: _q(step_size_qty.get((size, s.key)))
                for s in g_steps
            }
            done += _group_output(
                group_key=grp.key,
                step_qty=step_qty,
                group_steps=g_steps,
                required_keys=required,
            )
        incoming = plan
        remaining = plan - done
        if remaining < 0:
            remaining = Decimal("0")
        waiting = remaining
        if remaining > 0:
            waiting_total += remaining
            if remaining > bottleneck_qty:
                bottleneck_qty = remaining
                bottleneck = grp.label
        cells.append(
            TeamHandoverCell(
                group_key=grp.key,
                slug=slug,
                label=grp.label,
                plan=plan,
                done=done,
                waiting=waiting,
                incoming=incoming,
                status=_cell_status(done=done, plan=plan),
            )
        )

    return MoHandoverRow(
        mo=mo,
        plan=plan,
        cells=cells,
        waiting_total=waiting_total,
        bottleneck=bottleneck,
    )


def attach_qc_to_handover_rows(rows: list[MoHandoverRow]) -> list[MoHandoverRow]:
    """Gắn trạng thái QC theo tổ Ob lên từng ô bàn giao."""
    if not rows:
        return rows
    from san_xuat.services.qc import (
        QC_STATUS_SKIP,
        latest_qc_inspection_ids_for_mos,
        ob_qc_teams,
        qc_status_map_for_mos,
    )

    mos = [r.mo for r in rows]
    status_map = qc_status_map_for_mos(mos)
    insp_ids = latest_qc_inspection_ids_for_mos(mos)
    required_by_mo: dict[int, set[str]] = {}
    for mo in mos:
        required_by_mo[mo.pk] = {t.slug for t in ob_qc_teams(mo=mo)}
    for row in rows:
        required = required_by_mo.get(row.mo.pk, set())
        row.qc_inspection_id = insp_ids.get(row.mo.pk)
        for c in row.cells:
            c.qc_required = c.slug in required
            c.qc_inspection_id = row.qc_inspection_id if c.qc_required else None
            if not c.qc_required:
                c.qc_status = QC_STATUS_SKIP
            else:
                c.qc_status = status_map.get((row.mo.pk, c.slug), "idle")
    return rows


def attach_gc_to_handover_rows(rows: list[MoHandoverRow]) -> list[MoHandoverRow]:
    """Gắn phiếu thuê GC còn hiệu lực lên từng ô tổ."""
    if not rows:
        return rows
    from san_xuat.hub_models import SxSubcontractOrder

    mo_ids = [r.mo.pk for r in rows]
    qs = (
        SxSubcontractOrder.objects.filter(
            is_demo=False,
            production_order_id__in=mo_ids,
        )
        .exclude(status=SxSubcontractOrder.STATUS_CANCELLED)
        .order_by('-order_date', '-pk')
    )
    latest: dict[tuple[int, str], SxSubcontractOrder] = {}
    for order in qs:
        key = (order.production_order_id, (order.team_slug or '').strip().lower())
        if key[1] and key not in latest:
            latest[key] = order
    for row in rows:
        for c in row.cells:
            c.subcontract = latest.get((row.mo.pk, c.slug))
    return rows


def _participating_slugs(mo: SxProductionOrder) -> set[str]:
    from san_xuat.services.qc import ob_qc_teams

    return {t.slug for t in ob_qc_teams(mo=mo)}


def build_mo_handover_row(mo: SxProductionOrder) -> MoHandoverRow:
    all_steps = progress_steps()
    sizes = _size_plans(mo)
    stats = SxProductionStat.objects.filter(
        production_order=mo,
        is_demo=False,
        status=SxProductionStat.STATUS_CONFIRMED,
    ).only("process_name", "size_label", "qty_good")
    step_size_qty = _accumulate_stats(stats, sizes)
    row = _build_row(
        mo,
        sizes=sizes,
        step_size_qty=step_size_qty,
        all_steps=all_steps,
        participating_slugs=_participating_slugs(mo),
    )
    attach_qc_to_handover_rows([row])
    attach_gc_to_handover_rows([row])
    return row


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
        .select_related("sales_order", "bom_version", "routing")
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
        rows.append(
            _build_row(
                mo,
                sizes=sizes,
                step_size_qty=acc,
                all_steps=all_steps,
                participating_slugs=_participating_slugs(mo),
            )
        )
    attach_qc_to_handover_rows(rows)

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
