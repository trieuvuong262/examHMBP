"""Dashboard tổng quan hub Sản xuất — KPI + series biểu đồ từ dữ liệu thật."""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, F, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from san_xuat.hub_models import (
    SxDowntimeEvent,
    SxOverallPlan,
    SxProductionOrder,
    SxProductionStat,
    SxQcAlert,
    SxQcInspection,
    SxQcRequest,
)
from san_xuat.models import ProductTechDoc


def _d(v) -> Decimal:
    if v is None:
        return Decimal("0")
    return Decimal(str(v))


def parse_overview_period(
    *,
    month: str = "",
    date_from: str = "",
    date_to: str = "",
) -> tuple[date, date]:
    """Trả (date_from, date_to) inclusive. Mặc định: tháng hiện tại."""
    today = timezone.localdate()

    if (date_from or "").strip() and (date_to or "").strip():
        try:
            d0 = date.fromisoformat(date_from.strip())
            d1 = date.fromisoformat(date_to.strip())
            if d0 <= d1:
                return d0, d1
        except ValueError:
            pass

    month = (month or "").strip()
    if month:
        try:
            y, m = month.split("-", 1)
            year, mon = int(y), int(m)
            last = monthrange(year, mon)[1]
            return date(year, mon, 1), date(year, mon, last)
        except (ValueError, IndexError):
            pass

    return date(today.year, today.month, 1), today


@dataclass
class OverviewDashboard:
    date_from: date
    date_to: date
    product_code: str = ""

    # KPI
    doc_total: int = 0
    doc_active: int = 0
    plan_count: int = 0
    mo_open: int = 0
    mo_done: int = 0
    mo_total: int = 0
    mo_completion_pct: float = 0.0
    qty_planned: Decimal = field(default_factory=lambda: Decimal("0"))
    qty_done: Decimal = field(default_factory=lambda: Decimal("0"))
    qty_remaining: Decimal = field(default_factory=lambda: Decimal("0"))
    qty_good_period: Decimal = field(default_factory=lambda: Decimal("0"))
    qty_defect_period: Decimal = field(default_factory=lambda: Decimal("0"))
    defect_rate_pct: float = 0.0
    qc_open_requests: int = 0
    qc_pending: int = 0
    qc_pass: int = 0
    qc_fail: int = 0
    open_qc_alerts: int = 0

    # Charts / tables
    mo_by_status: list[dict] = field(default_factory=list)
    production_by_day: list[dict] = field(default_factory=list)
    top_products_output: list[dict] = field(default_factory=list)
    top_products_defect: list[dict] = field(default_factory=list)
    team_output: list[dict] = field(default_factory=list)
    process_output: list[dict] = field(default_factory=list)
    recent_alerts: list = field(default_factory=list)
    downtime_by_reason: list[dict] = field(default_factory=list)
    downtime_minutes_total: int = 0
    orders_by_sx_status: list[dict] = field(default_factory=list)


def build_overview_dashboard(
    *,
    date_from: date,
    date_to: date,
    product_code: str = "",
    team_label: str = "",
) -> OverviewDashboard:
    product_code = (product_code or "").strip()
    team_label = (team_label or "").strip()
    dash = OverviewDashboard(
        date_from=date_from,
        date_to=date_to,
        product_code=product_code,
    )

    dash.doc_total = ProductTechDoc.objects.count()
    dash.doc_active = ProductTechDoc.objects.filter(is_active=True).count()
    dash.plan_count = SxOverallPlan.objects.filter(is_demo=False).count()

    mo_qs = SxProductionOrder.objects.filter(is_demo=False)
    if product_code:
        mo_qs = mo_qs.filter(product_code__iexact=product_code)
    if team_label:
        mo_qs = mo_qs.filter(team_label__icontains=team_label)

    # LSX open / hoàn thành (toàn bộ active, không chỉ trong kỳ — khớp AMIS “chưa hoàn thành”)
    open_statuses = [
        SxProductionOrder.STATUS_DRAFT,
        SxProductionOrder.STATUS_RELEASED,
        SxProductionOrder.STATUS_IN_PROGRESS,
    ]
    dash.mo_open = mo_qs.filter(status__in=open_statuses).count()
    dash.mo_done = mo_qs.filter(status=SxProductionOrder.STATUS_DONE).count()
    dash.mo_total = mo_qs.exclude(status=SxProductionOrder.STATUS_CANCELLED).count()

    agg = mo_qs.exclude(status=SxProductionOrder.STATUS_CANCELLED).aggregate(
        planned=Coalesce(Sum("qty"), Decimal("0")),
        done=Coalesce(Sum("qty_done"), Decimal("0")),
    )
    dash.qty_planned = _d(agg["planned"])
    dash.qty_done = _d(agg["done"])
    dash.qty_remaining = max(dash.qty_planned - dash.qty_done, Decimal("0"))
    if dash.qty_planned > 0:
        dash.mo_completion_pct = float(
            (dash.qty_done / dash.qty_planned * Decimal("100")).quantize(Decimal("0.1"))
        )

    status_labels = dict(SxProductionOrder.STATUS_CHOICES)
    status_counts = {
        row["status"]: row["c"]
        for row in mo_qs.values("status").annotate(c=Count("id"))
    }
    dash.mo_by_status = [
        {
            "status": code,
            "label": status_labels.get(code, code),
            "count": status_counts.get(code, 0),
        }
        for code, _label in SxProductionOrder.STATUS_CHOICES
    ]

    # TKSX trong kỳ
    stat_qs = SxProductionStat.objects.filter(
        is_demo=False,
        status=SxProductionStat.STATUS_CONFIRMED,
        stat_date__gte=date_from,
        stat_date__lte=date_to,
    )
    if product_code:
        stat_qs = stat_qs.filter(production_order__product_code__iexact=product_code)
    if team_label:
        stat_qs = stat_qs.filter(team_label__icontains=team_label)

    stat_agg = stat_qs.aggregate(
        good=Coalesce(Sum("qty_good"), Decimal("0")),
        defect=Coalesce(Sum("qty_defect"), Decimal("0")),
    )
    dash.qty_good_period = _d(stat_agg["good"])
    dash.qty_defect_period = _d(stat_agg["defect"])
    produced = dash.qty_good_period + dash.qty_defect_period
    if produced > 0:
        dash.defect_rate_pct = float(
            (dash.qty_defect_period / produced * Decimal("100")).quantize(Decimal("0.1"))
        )

    # Sản lượng theo ngày (điền đủ ngày trong kỳ, tối đa 62 ngày để chart gọn)
    span_days = (date_to - date_from).days + 1
    day_map = {
        row["day"]: (_d(row["good"]), _d(row["defect"]))
        for row in (
            stat_qs.annotate(day=TruncDate("stat_date"))
            .values("day")
            .annotate(
                good=Coalesce(Sum("qty_good"), Decimal("0")),
                defect=Coalesce(Sum("qty_defect"), Decimal("0")),
            )
        )
        if row["day"]
    }
    if span_days <= 62:
        cursor = date_from
        while cursor <= date_to:
            good, defect = day_map.get(cursor, (Decimal("0"), Decimal("0")))
            dash.production_by_day.append({
                "date": cursor.isoformat(),
                "label": cursor.strftime("%d/%m"),
                "qty_good": float(good),
                "qty_defect": float(defect),
            })
            cursor += timedelta(days=1)
    else:
        for day in sorted(day_map.keys()):
            good, defect = day_map[day]
            dash.production_by_day.append({
                "date": day.isoformat(),
                "label": day.strftime("%d/%m"),
                "qty_good": float(good),
                "qty_defect": float(defect),
            })

    # Top SP sản lượng / lỗi từ TKSX kỳ
    top_base = (
        stat_qs.values(
            product_code=F("production_order__product_code"),
            product_name=F("production_order__product_name"),
        )
        .annotate(
            good=Coalesce(Sum("qty_good"), Decimal("0")),
            defect=Coalesce(Sum("qty_defect"), Decimal("0")),
        )
        .order_by()
    )
    dash.top_products_output = [
        {
            "product_code": r["product_code"] or "—",
            "product_name": r["product_name"] or "",
            "qty_good": float(_d(r["good"])),
            "qty_defect": float(_d(r["defect"])),
        }
        for r in sorted(top_base, key=lambda x: _d(x["good"]), reverse=True)[:10]
        if _d(r["good"]) > 0 or _d(r["defect"]) > 0
    ]
    dash.top_products_defect = [
        {
            "product_code": r["product_code"] or "—",
            "product_name": r["product_name"] or "",
            "qty_good": float(_d(r["good"])),
            "qty_defect": float(_d(r["defect"])),
            "defect_rate": float(
                (_d(r["defect"]) / (_d(r["good"]) + _d(r["defect"])) * Decimal("100")).quantize(
                    Decimal("0.1")
                )
            )
            if (_d(r["good"]) + _d(r["defect"])) > 0
            else 0.0,
        }
        for r in sorted(top_base, key=lambda x: _d(x["defect"]), reverse=True)[:10]
        if _d(r["defect"]) > 0
    ]

    dash.team_output = []
    for row in (
        stat_qs.exclude(team_label="")
        .values("team_label")
        .annotate(
            good=Coalesce(Sum("qty_good"), Decimal("0")),
            defect=Coalesce(Sum("qty_defect"), Decimal("0")),
        )
        .order_by("-good")[:12]
    ):
        good = float(_d(row["good"]))
        defect = float(_d(row["defect"]))
        tot = good + defect
        dash.team_output.append({
            "team_label": row["team_label"] or "—",
            "qty_good": good,
            "qty_defect": defect,
            "defect_rate": round(defect / tot * 100, 1) if tot else 0.0,
        })

    dash.process_output = []
    for row in (
        stat_qs.exclude(process_name="")
        .values("process_name")
        .annotate(
            good=Coalesce(Sum("qty_good"), Decimal("0")),
            defect=Coalesce(Sum("qty_defect"), Decimal("0")),
        )
        .order_by("-good")[:12]
    ):
        good = float(_d(row["good"]))
        defect = float(_d(row["defect"]))
        tot = good + defect
        dash.process_output.append({
            "process_name": row["process_name"],
            "qty_good": good,
            "qty_defect": defect,
            "defect_rate": round(defect / tot * 100, 1) if tot else 0.0,
        })

    # QC
    qc_req = SxQcRequest.objects.filter(is_demo=False)
    if product_code:
        qc_req = qc_req.filter(product_code__iexact=product_code)
    dash.qc_open_requests = qc_req.filter(status="open").count()

    qc_insp = SxQcInspection.objects.filter(
        is_demo=False,
        inspected_at__gte=date_from,
        inspected_at__lte=date_to,
    )
    if product_code:
        qc_insp = qc_insp.filter(qc_request__product_code__iexact=product_code)

    dash.qc_pending = qc_insp.filter(result=SxQcInspection.RESULT_PENDING).count()
    dash.qc_pass = qc_insp.filter(result=SxQcInspection.RESULT_PASS).count()
    dash.qc_fail = qc_insp.filter(result=SxQcInspection.RESULT_FAIL).count()

    alert_qs = SxQcAlert.objects.filter(is_demo=False, status=SxQcAlert.STATUS_OPEN)
    if product_code:
        alert_qs = alert_qs.filter(production_order__product_code__iexact=product_code)
    dash.open_qc_alerts = alert_qs.count()
    dash.recent_alerts = list(alert_qs.select_related("production_order").order_by("-pk")[:8])

    # Dừng chuyền theo lý do
    dt_qs = SxDowntimeEvent.objects.filter(
        is_demo=False,
        event_date__gte=date_from,
        event_date__lte=date_to,
    )
    if team_label:
        dt_qs = dt_qs.filter(team_label__icontains=team_label)
    dt_agg = (
        dt_qs.values("reason")
        .annotate(minutes=Coalesce(Sum("minutes"), 0), events=Count("id"))
        .order_by("-minutes")[:10]
    )
    total_dt = int(
        dt_qs.aggregate(t=Coalesce(Sum("minutes"), 0))["t"] or 0
    )
    dash.downtime_minutes_total = total_dt
    dash.downtime_by_reason = [
        {
            "reason": r["reason"] or "Không ghi rõ",
            "minutes": int(r["minutes"] or 0),
            "events": r["events"],
            "pct": round(100.0 * int(r["minutes"] or 0) / total_dt, 1) if total_dt else 0.0,
        }
        for r in dt_agg
    ]

    # Đơn ĐH (KHTT nguồn SO) theo trạng thái SX — proxy qua LSX trong kỳ
    mo_period = SxProductionOrder.objects.filter(
        is_demo=False,
        order_date__gte=date_from,
        order_date__lte=date_to,
    )
    if product_code:
        mo_period = mo_period.filter(product_code__iexact=product_code)
    if team_label:
        mo_period = mo_period.filter(team_label__icontains=team_label)
    status_labels = dict(SxProductionOrder.STATUS_CHOICES)
    dash.orders_by_sx_status = [
        {
            "status": row["status"],
            "label": status_labels.get(row["status"], row["status"]),
            "count": row["c"],
        }
        for row in mo_period.values("status").annotate(c=Count("id")).order_by()
    ]

    return dash
