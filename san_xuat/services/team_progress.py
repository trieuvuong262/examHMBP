"""Giám sát tiến độ theo tổ — bảng điều khiển cho kế hoạch / giám đốc.

Gộp KHCT (kế hoạch ngày), lệnh SX đang mở, TKSX đã xác nhận, dừng chuyền, cảnh báo QC
theo tổ/chuyền (`SxWorkCenter` + `team_label`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from urllib.parse import urlencode

from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone

from san_xuat.hub_models import (
    SxDetailPlanLine,
    SxDowntimeEvent,
    SxOverallPlan,
    SxProductionOrder,
    SxProductionStat,
    SxQcAlert,
    SxWorkCenter,
)


def _d(v) -> Decimal:
    if v is None:
        return Decimal("0")
    return Decimal(str(v))


def _norm(label: str) -> str:
    return (label or "").strip()


def team_aliases(center: SxWorkCenter) -> set[str]:
    """Các nhãn có thể khớp TKSX / LSX / KHCT với một work center."""
    out: set[str] = set()
    for raw in (center.team_label, center.name, center.code):
        t = _norm(raw)
        if t:
            out.add(t)
            out.add(t.lower())
    return out


def resolve_team_key(label: str, *, centers: list[SxWorkCenter]) -> str:
    """Chuẩn hoá nhãn tổ về mã work center nếu khớp; không thì giữ nguyên."""
    t = _norm(label)
    if not t:
        return ""
    lower = t.lower()
    for wc in centers:
        aliases = team_aliases(wc)
        if t in aliases or lower in aliases:
            return wc.code
    return t


def _sx_url(name: str, *, pk: int | None = None, query: dict | None = None) -> str:
    if pk is not None:
        path = reverse(f"san_xuat:{name}", kwargs={"pk": pk})
    else:
        path = reverse(f"san_xuat:{name}")
    if not query:
        return path
    cleaned = {k: v for k, v in query.items() if v not in (None, "")}
    if not cleaned:
        return path
    return f"{path}?{urlencode(cleaned)}"


def _period_query(date_from: date, date_to: date, **extra) -> dict:
    q = {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
    }
    q.update(extra)
    return q


@dataclass
class TeamMoBrief:
    pk: int
    code: str
    product_code: str
    qty: Decimal
    qty_done: Decimal
    status: str
    status_label: str
    due_date: date | None
    progress_pct: float
    is_late: bool


@dataclass
class TeamProgressAlert:
    kind: str
    message: str
    severity: str  # warn | danger
    url: str = ""
    action_label: str = ""


@dataclass
class TeamProgressRow:
    team_key: str
    team_label: str
    work_center: SxWorkCenter | None
    qty_planned: Decimal = field(default_factory=lambda: Decimal("0"))
    qty_good: Decimal = field(default_factory=lambda: Decimal("0"))
    qty_defect: Decimal = field(default_factory=lambda: Decimal("0"))
    progress_pct: float = 0.0
    defect_rate_pct: float = 0.0
    mo_open: int = 0
    mo_late: int = 0
    downtime_minutes: int = 0
    qc_alerts_open: int = 0
    status: str = "idle"  # ok | warn | danger | idle
    mos: list[TeamMoBrief] = field(default_factory=list)
    alerts: list[TeamProgressAlert] = field(default_factory=list)
    action_url: str = ""
    action_label: str = ""

    @property
    def progress_bar_pct(self) -> int:
        try:
            return max(0, min(100, int(round(float(self.progress_pct)))))
        except (TypeError, ValueError):
            return 0


@dataclass
class TeamProgressBoard:
    date_from: date
    date_to: date
    team_filter: str = ""
    product_code: str = ""
    rows: list[TeamProgressRow] = field(default_factory=list)
    teams_total: int = 0
    teams_active: int = 0
    teams_late: int = 0
    teams_no_output: int = 0
    qty_planned_total: Decimal = field(default_factory=lambda: Decimal("0"))
    qty_good_total: Decimal = field(default_factory=lambda: Decimal("0"))
    qty_defect_total: Decimal = field(default_factory=lambda: Decimal("0"))
    progress_pct_overall: float = 0.0
    downtime_minutes_total: int = 0
    qc_alerts_open: int = 0


def _mo_progress_pct(mo: SxProductionOrder) -> float:
    qty = _d(mo.qty)
    if qty <= 0:
        return 0.0
    return round(float(_d(mo.qty_done) / qty * 100), 1)


def _row_status(row: TeamProgressRow) -> str:
    if row.mo_late or row.qc_alerts_open:
        return "danger"
    if row.alerts:
        return "warn"
    if row.mo_open or row.qty_good > 0 or row.qty_planned > 0:
        return "ok"
    return "idle"


def _matches_team_filter(display: str, key: str, team_filter: str) -> bool:
    if not team_filter:
        return True
    f = team_filter.lower()
    return f in (display or "").lower() or f in (key or "").lower()


def build_team_progress_board(
    *,
    date_from: date,
    date_to: date,
    team_label: str = "",
    product_code: str = "",
) -> TeamProgressBoard:
    today = timezone.localdate()
    team_filter = _norm(team_label)
    product_code = _norm(product_code)

    board = TeamProgressBoard(
        date_from=date_from,
        date_to=date_to,
        team_filter=team_filter,
        product_code=product_code,
    )

    centers = list(
        SxWorkCenter.objects.filter(is_demo=False, is_active=True).order_by("code")
    )
    center_by_code = {wc.code: wc for wc in centers}

    rows_map: dict[str, TeamProgressRow] = {}
    for wc in centers:
        # Bỏ tổ hỗ trợ / chưa khai NL (SP/ngày = 0) khỏi danh sách mặc định —
        # chỉ hiện nếu có KHCT / LSX / TKSX gắn vào.
        if (wc.capacity_per_day or Decimal("0")) <= 0:
            continue
        display = _norm(wc.team_label) or _norm(wc.name) or wc.code
        if not _matches_team_filter(display, wc.code, team_filter):
            continue
        rows_map[wc.code] = TeamProgressRow(
            team_key=wc.code,
            team_label=display,
            work_center=wc,
        )

    def ensure_row(label: str) -> TeamProgressRow | None:
        raw = _norm(label) or "(Chưa gắn tổ)"
        key = resolve_team_key(raw, centers=centers) or raw
        wc = center_by_code.get(key)
        display = (_norm(wc.team_label) or _norm(wc.name) or wc.code) if wc else raw
        if not _matches_team_filter(display, key, team_filter):
            return None
        if key in rows_map:
            return rows_map[key]
        rows_map[key] = TeamProgressRow(
            team_key=key,
            team_label=display,
            work_center=wc,
        )
        return rows_map[key]

    # --- Kế hoạch chi tiết (không nháp / hủy) ---
    plan_line_qs = (
        SxDetailPlanLine.objects.filter(
            plan__is_demo=False,
            plan_date__gte=date_from,
            plan_date__lte=date_to,
        )
        .exclude(plan__status=SxOverallPlan.STATUS_CANCELLED)
        .exclude(plan__status=SxOverallPlan.STATUS_DRAFT)
        .select_related("work_center")
    )
    if product_code:
        plan_line_qs = plan_line_qs.filter(product_code__icontains=product_code)

    for line in plan_line_qs:
        label = ""
        if line.work_center_id:
            wc = line.work_center
            label = _norm(wc.team_label) or _norm(wc.name) or wc.code
        if not label:
            label = _norm(line.team_label)
        row = ensure_row(label)
        if row is None:
            continue
        row.qty_planned += _d(line.qty)

    # --- Lệnh SX ---
    open_statuses = [
        SxProductionOrder.STATUS_DRAFT,
        SxProductionOrder.STATUS_RELEASED,
        SxProductionOrder.STATUS_IN_PROGRESS,
    ]
    mo_qs = SxProductionOrder.objects.filter(is_demo=False).exclude(
        status=SxProductionOrder.STATUS_CANCELLED,
    )
    if product_code:
        mo_qs = mo_qs.filter(product_code__icontains=product_code)

    mo_period = mo_qs.filter(
        Q(status__in=open_statuses)
        | Q(order_date__gte=date_from, order_date__lte=date_to)
        | Q(planned_start__lte=date_to, planned_end__gte=date_from)
    ).distinct()

    status_labels = dict(SxProductionOrder.STATUS_CHOICES)
    for mo in mo_period.order_by("due_date", "code"):
        row = ensure_row(mo.team_label)
        if row is None:
            continue
        is_open = mo.status in open_statuses
        is_late = bool(
            is_open
            and mo.due_date
            and mo.due_date < today
        )
        if is_open:
            row.mo_open += 1
        if is_late:
            row.mo_late += 1
        if is_open and len(row.mos) < 8:
            row.mos.append(
                TeamMoBrief(
                    pk=mo.pk,
                    code=mo.code,
                    product_code=mo.product_code,
                    qty=_d(mo.qty),
                    qty_done=_d(mo.qty_done),
                    status=mo.status,
                    status_label=status_labels.get(mo.status, mo.status),
                    due_date=mo.due_date,
                    progress_pct=_mo_progress_pct(mo),
                    is_late=is_late,
                )
            )

    # --- TKSX đã xác nhận trong kỳ ---
    stat_qs = SxProductionStat.objects.filter(
        is_demo=False,
        status=SxProductionStat.STATUS_CONFIRMED,
        stat_date__gte=date_from,
        stat_date__lte=date_to,
    )
    if product_code:
        stat_qs = stat_qs.filter(production_order__product_code__icontains=product_code)

    for agg in stat_qs.values("team_label").annotate(
        good=Coalesce(Sum("qty_good"), Decimal("0")),
        defect=Coalesce(Sum("qty_defect"), Decimal("0")),
    ):
        row = ensure_row(agg["team_label"])
        if row is None:
            continue
        row.qty_good += _d(agg["good"])
        row.qty_defect += _d(agg["defect"])

    # --- Dừng chuyền ---
    dt_qs = SxDowntimeEvent.objects.filter(
        is_demo=False,
        event_date__gte=date_from,
        event_date__lte=date_to,
    ).select_related("work_center")
    for ev in dt_qs:
        label = ""
        if ev.work_center_id:
            wc = ev.work_center
            label = _norm(wc.team_label) or _norm(wc.name) or wc.code
        if not label:
            label = _norm(ev.team_label)
        row = ensure_row(label)
        if row is None:
            continue
        row.downtime_minutes += int(ev.minutes or 0)

    # --- Cảnh báo QC mở ---
    alert_qs = SxQcAlert.objects.filter(
        is_demo=False,
        status=SxQcAlert.STATUS_OPEN,
    ).select_related("production_order")
    if product_code:
        alert_qs = alert_qs.filter(production_order__product_code__icontains=product_code)
    for alert in alert_qs:
        mo = alert.production_order
        row = ensure_row(mo.team_label if mo else "")
        if row is None:
            continue
        row.qc_alerts_open += 1

    # --- % / cảnh báo / KPI ---
    rows: list[TeamProgressRow] = []
    for row in rows_map.values():
        if row.qty_planned > 0:
            row.progress_pct = round(float(row.qty_good / row.qty_planned * 100), 1)
        elif row.mos:
            row.progress_pct = round(
                sum(m.progress_pct for m in row.mos) / len(row.mos),
                1,
            )
        total_out = row.qty_good + row.qty_defect
        row.defect_rate_pct = (
            round(float(row.qty_defect / total_out * 100), 1) if total_out else 0.0
        )

        alerts: list[TeamProgressAlert] = []
        team_name = row.team_label if row.team_label != "(Chưa gắn tổ)" else ""
        late_mo = next((m for m in row.mos if m.is_late), None)
        first_mo = row.mos[0] if row.mos else None

        if row.mo_late:
            late_url = (
                _sx_url("dispatch_mo_detail", pk=late_mo.pk)
                if late_mo
                else _sx_url(
                    "dispatch_mo",
                    query=_period_query(date_from, date_to, name=team_name),
                )
            )
            alerts.append(
                TeamProgressAlert(
                    kind="late",
                    message=f"{row.mo_late} lệnh quá hạn",
                    severity="danger",
                    url=late_url,
                    action_label="Xem lệnh trễ",
                )
            )
        if row.qc_alerts_open:
            alerts.append(
                TeamProgressAlert(
                    kind="qc",
                    message=f"{row.qc_alerts_open} cảnh báo QC mở",
                    severity="danger",
                    url=_sx_url(
                        "qc_alerts",
                        query={"status": SxQcAlert.STATUS_OPEN, "name": team_name},
                    ),
                    action_label="Xử lý QC",
                )
            )
        if row.qty_planned > 0 and row.qty_good <= 0 and date_to >= today:
            if first_mo:
                no_out_url = _sx_url(
                    "dispatch_prod_stats_create",
                    query={"mo": first_mo.pk},
                )
            else:
                no_out_url = _sx_url(
                    "dispatch_prod_stats",
                    query=_period_query(date_from, date_to, name=team_name),
                )
            alerts.append(
                TeamProgressAlert(
                    kind="no_output",
                    message="Có kế hoạch nhưng chưa ghi nhận sản lượng",
                    severity="warn",
                    url=no_out_url,
                    action_label="Ghi nhận TKSX",
                )
            )
        if row.downtime_minutes >= 60:
            alerts.append(
                TeamProgressAlert(
                    kind="downtime",
                    message=f"Dừng chuyền {row.downtime_minutes} phút",
                    severity="warn",
                    url=_sx_url(
                        "downtime_list",
                        query=_period_query(date_from, date_to, name=team_name),
                    ),
                    action_label="Xem dừng chuyền",
                )
            )
        if row.defect_rate_pct >= 5 and total_out > 0:
            alerts.append(
                TeamProgressAlert(
                    kind="defect",
                    message=f"Tỷ lệ lỗi {row.defect_rate_pct}%",
                    severity="warn",
                    url=_sx_url(
                        "dispatch_prod_stats",
                        query=_period_query(date_from, date_to, name=team_name),
                    ),
                    action_label="Xem thống kê SX",
                )
            )
        row.alerts = alerts
        row.status = _row_status(row)

        # CTA chính: ưu tiên cảnh báo đầu (đã xếp danger trước), không thì lệnh / KH / năng lực
        if alerts:
            row.action_url = alerts[0].url
            row.action_label = alerts[0].action_label or "Xử lý"
        elif first_mo:
            row.action_url = _sx_url("dispatch_mo_detail", pk=first_mo.pk)
            row.action_label = "Xem lệnh SX"
        elif row.qty_planned > 0:
            row.action_url = _sx_url(
                "plan_detail",
                query=_period_query(date_from, date_to, name=team_name),
            )
            row.action_label = "Xem kế hoạch chi tiết"
        else:
            wc = row.work_center
            has_cap = bool(
                wc
                and (
                    (wc.capacity_per_day or Decimal("0")) > 0
                    or wc.available_minutes_per_day > 0
                )
            )
            row.action_url = _sx_url(
                "capacity_list",
                query={"name": team_name} if team_name else None,
            )
            row.action_label = "Xem năng lực tổ" if has_cap else "Khai năng lực tổ"

        rows.append(row)

    rank = {"danger": 0, "warn": 1, "ok": 2, "idle": 3}
    rows.sort(key=lambda r: (rank.get(r.status, 9), r.progress_pct, r.team_label.lower()))

    board.rows = rows
    board.teams_total = len(rows)
    board.teams_active = sum(
        1 for r in rows if r.mo_open or r.qty_good > 0 or r.qty_planned > 0
    )
    board.teams_late = sum(1 for r in rows if r.mo_late)
    board.teams_no_output = sum(1 for r in rows if r.qty_planned > 0 and r.qty_good <= 0)
    board.qty_planned_total = sum((r.qty_planned for r in rows), Decimal("0"))
    board.qty_good_total = sum((r.qty_good for r in rows), Decimal("0"))
    board.qty_defect_total = sum((r.qty_defect for r in rows), Decimal("0"))
    if board.qty_planned_total > 0:
        board.progress_pct_overall = round(
            float(board.qty_good_total / board.qty_planned_total * 100),
            1,
        )
    board.downtime_minutes_total = sum(r.downtime_minutes for r in rows)
    board.qc_alerts_open = sum(r.qc_alerts_open for r in rows)
    return board
