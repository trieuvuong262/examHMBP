"""Tiến độ lệnh sản xuất: checklist bước + so sánh kế hoạch vs thực tế + thiếu bước truy xuất."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Sum

from kho_npl.choices import DOC_STATUS_POSTED
from san_xuat.hub_models import (
    SxFgReceiptRequest,
    SxMaterialIssueRequest,
    SxProductionOrder,
    SxProductionStat,
    SxQcInspection,
)


@dataclass
class ProgressStep:
    key: str
    label: str
    done: bool
    detail: str = ""
    url_name: str = ""
    url_pk: int | None = None
    optional: bool = False


@dataclass
class QtyCompareRow:
    label: str
    planned: Decimal
    actual: Decimal

    @property
    def variance(self) -> Decimal:
        return (self.actual or Decimal("0")) - (self.planned or Decimal("0"))

    @property
    def pct(self) -> float | None:
        planned = self.planned or Decimal("0")
        if planned <= 0:
            return None
        return float((self.actual or Decimal("0")) / planned * 100)


@dataclass
class MoProgress:
    mo: SxProductionOrder
    steps: list[ProgressStep] = field(default_factory=list)
    qty_rows: list[QtyCompareRow] = field(default_factory=list)
    done_count: int = 0
    total_steps: int = 0
    qc_passed: int = 0
    qc_total: int = 0
    qc_next_slug: str = ""
    qc_inspection_id: int | None = None

    @property
    def pct_complete(self) -> int:
        if not self.total_steps:
            return 0
        return int(round(100 * self.done_count / self.total_steps))

    def _step_done(self, key: str) -> bool:
        return any(s.key == key and s.done for s in self.steps)

    @property
    def issue_done(self) -> bool:
        return self._step_done("issue")

    @property
    def stat_done(self) -> bool:
        return self._step_done("stat")

    @property
    def fg_done(self) -> bool:
        return self._step_done("fg")

    @property
    def qc_done(self) -> bool:
        return self._step_done("qc")

    @property
    def next_qc_slug(self) -> str:
        return self.qc_next_slug


@dataclass
class TraceGap:
    key: str
    label: str
    hint: str
    url_name: str = ""
    url_pk: int | None = None


def _dec(val) -> Decimal:
    if val is None:
        return Decimal("0")
    return Decimal(str(val))


def _qty_issued(mo: SxProductionOrder) -> Decimal:
    total = Decimal("0")
    for req in SxMaterialIssueRequest.objects.filter(is_demo=False, production_order=mo).prefetch_related("lines"):
        for line in req.lines.all():
            total += _dec(line.qty_issued)
    return total


def _qty_requested_npl(mo: SxProductionOrder) -> Decimal:
    total = Decimal("0")
    for req in SxMaterialIssueRequest.objects.filter(is_demo=False, production_order=mo).prefetch_related("lines"):
        for line in req.lines.all():
            total += _dec(line.qty_requested)
    return total


def _qty_good_confirmed(mo: SxProductionOrder) -> Decimal:
    agg = SxProductionStat.objects.filter(
        is_demo=False,
        production_order=mo,
        status=SxProductionStat.STATUS_CONFIRMED,
    ).aggregate(s=Sum("qty_good"))
    return _dec(agg["s"])


def _qty_fg(mo: SxProductionOrder) -> Decimal:
    agg = SxFgReceiptRequest.objects.filter(
        is_demo=False,
        production_order=mo,
    ).exclude(status=SxFgReceiptRequest.STATUS_CANCELLED).aggregate(s=Sum("qty"))
    return _dec(agg["s"])


def _has_posted_issue(mo: SxProductionOrder) -> tuple[bool, SxMaterialIssueRequest | None]:
    qs = (
        SxMaterialIssueRequest.objects.filter(is_demo=False, production_order=mo)
        .select_related("stock_issue")
        .order_by("-pk")
    )
    for req in qs:
        if req.status == "done":
            return True, req
        if req.stock_issue_id and getattr(req.stock_issue, "status", "") == DOC_STATUS_POSTED:
            return True, req
    first = qs.first()
    return False, first


def _has_qc_pass(mo: SxProductionOrder) -> tuple[bool, SxQcInspection | None]:
    from san_xuat.services.qc import latest_qc_inspection, qc_ready_for_fg

    ok, _msg = qc_ready_for_fg(mo=mo)
    return ok, latest_qc_inspection(mo=mo)


def build_mo_progress(mo: SxProductionOrder) -> MoProgress:
    planned = _dec(mo.qty)
    issued_ok, issue_req = _has_posted_issue(mo)
    stat = (
        SxProductionStat.objects.filter(
            is_demo=False,
            production_order=mo,
            status=SxProductionStat.STATUS_CONFIRMED,
        )
        .order_by("-pk")
        .first()
    )
    _, qc_insp = _has_qc_pass(mo)
    fg = (
        SxFgReceiptRequest.objects.filter(is_demo=False, production_order=mo)
        .exclude(status=SxFgReceiptRequest.STATUS_CANCELLED)
        .order_by("-pk")
        .first()
    )

    released = mo.status in (
        SxProductionOrder.STATUS_RELEASED,
        SxProductionOrder.STATUS_IN_PROGRESS,
        SxProductionOrder.STATUS_DONE,
    )

    steps = [
        ProgressStep(
            key="created",
            label="Tạo lệnh sản xuất",
            done=True,
            detail=mo.code,
            url_name="san_xuat:dispatch_mo_detail",
            url_pk=mo.pk,
        ),
        ProgressStep(
            key="released",
            label="Phát hành lệnh",
            done=released,
            detail=mo.get_status_display(),
            url_name="san_xuat:dispatch_mo_detail",
            url_pk=mo.pk,
        ),
        ProgressStep(
            key="issue",
            label="Xuất nguyên phụ liệu (đã ghi sổ)",
            done=issued_ok,
            detail=issue_req.code if issue_req else "Chưa có yêu cầu xuất",
            url_name="san_xuat:dispatch_material_issue_req_detail" if issue_req else "",
            url_pk=issue_req.pk if issue_req else None,
        ),
        ProgressStep(
            key="stat",
            label="Thống kê sản xuất đã xác nhận",
            done=bool(stat),
            detail=f"{stat.code} · đạt {stat.qty_good}" if stat else "Chưa có",
            url_name="san_xuat:dispatch_prod_stats_detail" if stat else "san_xuat:dispatch_prod_stats_create",
            url_pk=stat.pk if stat else None,
        ),
    ]
    from san_xuat.services.qc import (
        QC_STATUS_PASS,
        latest_qc_inspection_ids_for_mos,
        ob_qc_progress,
        ob_qc_teams,
        qc_ready_for_fg,
        qc_status_map_for_mos,
    )

    qc_passed, qc_total, _missing = ob_qc_progress(mo=mo)
    qc_ok, _qc_block = qc_ready_for_fg(mo=mo)
    insp_id = latest_qc_inspection_ids_for_mos([mo]).get(mo.pk)
    next_slug = ""
    if qc_total and not qc_ok:
        status_map = qc_status_map_for_mos([mo])
        for team in ob_qc_teams(mo=mo):
            if status_map.get((mo.pk, team.slug)) != QC_STATUS_PASS:
                next_slug = team.slug
                break
    if qc_total:
        qc_label = f"Kiểm tra sản phẩm ({qc_passed}/{qc_total})"
        if qc_ok:
            qc_detail = "Đã chốt phiếu"
        elif qc_passed == qc_total:
            qc_detail = "Chưa chốt phiếu"
        else:
            qc_detail = f"Còn {qc_total - qc_passed} tổ"
    else:
        qc_label = "Kiểm tra sản phẩm"
        qc_detail = qc_insp.code if qc_insp else "Không có tổ Ob"
    steps.append(
        ProgressStep(
            key="qc",
            label=qc_label,
            done=qc_ok,
            detail=qc_detail,
            url_name="san_xuat:qc_sheet_detail" if insp_id else "san_xuat:qc_stub",
            url_pk=insp_id,
        )
    )
    qty_good = _qty_good_confirmed(mo)
    qty_fg = _qty_fg(mo)
    qty_iss = _qty_issued(mo)
    qty_req_npl = _qty_requested_npl(mo)

    def _qty_label(value: Decimal) -> str:
        if value == value.to_integral_value():
            return str(int(value))
        return format(value.normalize(), 'f')

    fg_done = planned > 0 and qty_fg >= planned
    steps.append(
        ProgressStep(
            key="fg",
            label=f"Nhập thành phẩm ({_qty_label(qty_fg)}/{_qty_label(planned)})",
            done=fg_done,
            detail=f"{fg.code} · {fg.get_status_display()}" if fg else "Chưa có",
            url_name="san_xuat:dispatch_fg_receipt_req_detail" if fg else "san_xuat:dispatch_fg_receipt_req_create",
            url_pk=fg.pk if fg else None,
        )
    )

    qty_rows = [
        QtyCompareRow("Số lượng lệnh (kế hoạch)", planned, planned),
        QtyCompareRow("Nguyên phụ liệu yêu cầu / đã xuất", qty_req_npl, qty_iss),
        QtyCompareRow("Sản lượng đạt (thống kê xác nhận)", planned, qty_good),
        QtyCompareRow("Nhập thành phẩm", planned, qty_fg),
    ]

    tracked = [s for s in steps if not s.optional]
    done_count = sum(1 for s in tracked if s.done)
    return MoProgress(
        mo=mo,
        steps=steps,
        qty_rows=qty_rows,
        done_count=done_count,
        total_steps=len(tracked),
        qc_passed=qc_passed,
        qc_total=qc_total,
        qc_next_slug=next_slug,
        qc_inspection_id=insp_id,
    )


def analyze_trace_gaps(*, mo: SxProductionOrder, timeline_len: int = 0, min_events: int = 4) -> list[TraceGap]:
    """Liệt kê bước còn thiếu trên chuỗi truy xuất của một lệnh."""
    progress = build_mo_progress(mo)
    gaps: list[TraceGap] = []
    hints = {
        "released": "Phát hành lệnh sản xuất trước khi xuất vật tư / ghi sản lượng.",
        "issue": "Tạo và duyệt yêu cầu xuất vật tư (phiếu xuất đã ghi sổ).",
        "stat": "Ghi và xác nhận thống kê sản xuất theo công đoạn.",
        "qc": "Hoàn tất Kiểm tra sản phẩm đủ tổ trên Ob trước khi nhập thành phẩm.",
        "fg": "Tạo / gửi yêu cầu nhập thành phẩm.",
    }
    for step in progress.steps:
        if step.key == "created" or step.done or step.optional:
            continue
        gaps.append(
            TraceGap(
                key=step.key,
                label=step.label,
                hint=(
                    hints.get(step.key)
                    or (hints["qc"] if step.key.startswith("qc_") else None)
                    or step.detail
                    or "Bổ sung bước này trên lệnh."
                ),
                url_name=step.url_name,
                url_pk=step.url_pk,
            )
        )

    if timeline_len < min_events and not gaps:
        gaps.append(
            TraceGap(
                key="timeline",
                label=f"Timeline còn mỏng ({timeline_len}/{min_events} sự kiện)",
                hint="Chuỗi sự kiện ít hơn ngưỡng — kiểm tra lại xuất kho, thống kê, kiểm tra, nhập thành phẩm.",
                url_name="san_xuat:dispatch_mo_detail",
                url_pk=mo.pk,
            )
        )
    return gaps


def pending_material_issue_qs():
    """Hàng đợi duyệt xuất: nháp/đã gửi và chưa có phiếu xuất."""
    return (
        SxMaterialIssueRequest.objects.filter(is_demo=False, stock_issue__isnull=True)
        .filter(status__in=("draft", "submitted", "approved", "partial"))
        .select_related("production_order")
        .order_by("request_date", "pk")
    )
