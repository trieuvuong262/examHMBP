"""Tiến độ lệnh sản xuất: checklist bước + so sánh kế hoạch vs thực tế + thiếu bước truy xuất."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Sum

from kho_npl.choices import DOC_STATUS_POSTED
from san_xuat.hub_models import (
    SxFgReceiptRequest,
    SxMaterialIssueRequest,
    SxPackingRecord,
    SxProductionOrder,
    SxProductionStat,
    SxQcInspection,
    SxQcRequest,
)


@dataclass
class ProgressStep:
    key: str
    label: str
    done: bool
    detail: str = ""
    url_name: str = ""
    url_pk: int | None = None


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
    def packing_done(self) -> bool:
        return self._step_done("packing")


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


def _qty_packing(mo: SxProductionOrder) -> Decimal:
    agg = SxPackingRecord.objects.filter(
        is_demo=False,
        production_order=mo,
        status=SxPackingRecord.STATUS_CONFIRMED,
    ).aggregate(s=Sum("qty"))
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
    insp = (
        SxQcInspection.objects.filter(
            is_demo=False,
            result=SxQcInspection.RESULT_PASS,
            qc_request__production_order=mo,
            qc_request__is_demo=False,
        )
        .order_by("-pk")
        .first()
    )
    return bool(insp), insp


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
    qc_ok, qc_insp = _has_qc_pass(mo)
    fg = (
        SxFgReceiptRequest.objects.filter(is_demo=False, production_order=mo)
        .exclude(status=SxFgReceiptRequest.STATUS_CANCELLED)
        .order_by("-pk")
        .first()
    )
    pack = (
        SxPackingRecord.objects.filter(
            is_demo=False,
            production_order=mo,
            status=SxPackingRecord.STATUS_CONFIRMED,
        )
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
        ProgressStep(
            key="qc",
            label="Kiểm tra chất lượng Đạt",
            done=qc_ok,
            detail=qc_insp.code if qc_insp else "Chưa có phiếu Đạt",
            url_name="san_xuat:qc_sheet_detail" if qc_insp else "san_xuat:qc_request",
            url_pk=qc_insp.pk if qc_insp else None,
        ),
        ProgressStep(
            key="fg",
            label="Nhập thành phẩm",
            done=bool(fg),
            detail=f"{fg.code} · {fg.get_status_display()}" if fg else "Chưa có",
            url_name="san_xuat:dispatch_fg_receipt_req_detail" if fg else "san_xuat:dispatch_fg_receipt_req_create",
            url_pk=fg.pk if fg else None,
        ),
        ProgressStep(
            key="packing",
            label="Đóng gói đã xác nhận",
            done=bool(pack),
            detail=f"{pack.code} · lô {pack.lot_code or '—'}" if pack else "Chưa có",
            url_name="san_xuat:packing_detail" if pack else "san_xuat:packing_create",
            url_pk=pack.pk if pack else None,
        ),
    ]

    qty_good = _qty_good_confirmed(mo)
    qty_fg = _qty_fg(mo)
    qty_pack = _qty_packing(mo)
    qty_iss = _qty_issued(mo)
    qty_req_npl = _qty_requested_npl(mo)

    qty_rows = [
        QtyCompareRow("Số lượng lệnh (kế hoạch)", planned, planned),
        QtyCompareRow("Nguyên phụ liệu yêu cầu / đã xuất", qty_req_npl, qty_iss),
        QtyCompareRow("Sản lượng đạt (thống kê xác nhận)", planned, qty_good),
        QtyCompareRow("Nhập thành phẩm", planned, qty_fg),
        QtyCompareRow("Đóng gói đã xác nhận", planned, qty_pack),
    ]

    done_count = sum(1 for s in steps if s.done)
    return MoProgress(
        mo=mo,
        steps=steps,
        qty_rows=qty_rows,
        done_count=done_count,
        total_steps=len(steps),
    )


def analyze_trace_gaps(*, mo: SxProductionOrder, timeline_len: int = 0, min_events: int = 4) -> list[TraceGap]:
    """Liệt kê bước còn thiếu trên chuỗi truy xuất của một lệnh."""
    progress = build_mo_progress(mo)
    gaps: list[TraceGap] = []
    hints = {
        "released": "Phát hành lệnh sản xuất trước khi xuất vật tư / ghi sản lượng.",
        "issue": "Tạo và duyệt yêu cầu xuất vật tư (phiếu xuất đã ghi sổ).",
        "stat": "Ghi và xác nhận thống kê sản xuất theo công đoạn.",
        "qc": "Tạo yêu cầu kiểm tra và chốt phiếu kiểm tra Đạt.",
        "fg": "Tạo / gửi yêu cầu nhập thành phẩm (liên kết KiotViet nếu dùng).",
        "packing": "Xác nhận phiếu đóng gói để có mã lô.",
    }
    for step in progress.steps:
        if step.key == "created" or step.done:
            continue
        gaps.append(
            TraceGap(
                key=step.key,
                label=step.label,
                hint=hints.get(step.key, step.detail or "Bổ sung bước này trên lệnh."),
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
