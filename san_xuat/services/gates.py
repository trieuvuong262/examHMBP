"""Cổng kiểm soát quy trình SX — ưu tiên thiết lập DB, fallback settings/env."""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from kho_npl.choices import DOC_STATUS_POSTED
from san_xuat.hub_models import (
    SxMaterialIssueRequest,
    SxPackingRecord,
    SxProductionOrder,
    SxProductionStat,
    SxQcAlert,
    SxQcInspection,
)
from san_xuat.services.dispatch import DispatchError
from san_xuat.services.sx_settings import sx_gate

MODE_OFF = "off"
MODE_WARN = "warn"
MODE_BLOCK = "block"
VALID_MODES = {MODE_OFF, MODE_WARN, MODE_BLOCK}

# settings key → field trên SxGeneralSettings (và sx_gate)
_GATE_FIELD_MAP = {
    "SX_GATE_REQUIRE_RELEASE_BEFORE_ISSUE": "gate_release_before_issue",
    "SX_GATE_REQUIRE_ISSUE_BEFORE_STAT": "gate_issue_before_stat",
    "SX_GATE_REQUIRE_STAT_BEFORE_FG": "gate_stat_before_fg",
    "SX_GATE_REQUIRE_QC_PASS_BEFORE_FG": "gate_qc_pass_before_fg",
    "SX_GATE_OPEN_QC_ALERT_BEFORE_FG": "gate_open_qc_alert_before_fg",
    "SX_GATE_PACKING_BEFORE_DONE": "gate_packing_before_done",
}


@dataclass(frozen=True)
class GateResult:
    ok: bool
    mode: str
    code: str
    message: str = ""

    @property
    def should_block(self) -> bool:
        return (not self.ok) and self.mode == MODE_BLOCK

    @property
    def should_warn(self) -> bool:
        return (not self.ok) and self.mode == MODE_WARN


def gate_mode(key: str, default: str = MODE_BLOCK) -> str:
    field = _GATE_FIELD_MAP.get(key)
    if field:
        db_val = sx_gate(field, default)
        if db_val in VALID_MODES:
            return db_val
    raw = (getattr(settings, key, None) or default or MODE_BLOCK)
    mode = str(raw).strip().lower()
    return mode if mode in VALID_MODES else default


def get_trace_min_timeline_events(default: int = 4) -> int:
    from san_xuat.services.sx_settings import sx_int

    return sx_int("trace_min_timeline_events", default, min_v=1, max_v=20)


def enforce_gate(result: GateResult) -> str | None:
    if result.ok or result.mode == MODE_OFF:
        return None
    if result.mode == MODE_BLOCK:
        raise DispatchError(result.message)
    return result.message


def check_released_before_issue(*, mo: SxProductionOrder) -> GateResult:
    mode = gate_mode("SX_GATE_REQUIRE_RELEASE_BEFORE_ISSUE", MODE_BLOCK)
    if mode == MODE_OFF:
        return GateResult(ok=True, mode=mode, code="release_before_issue")
    ok = mo.status in (
        SxProductionOrder.STATUS_RELEASED,
        SxProductionOrder.STATUS_IN_PROGRESS,
        SxProductionOrder.STATUS_DONE,
    )
    return GateResult(
        ok=ok,
        mode=mode,
        code="release_before_issue",
        message=(
            f"Lệnh {mo.code} chưa phát hành — không tạo yêu cầu xuất vật tư."
            if not ok
            else ""
        ),
    )


def _has_posted_material_issue(*, mo: SxProductionOrder) -> bool:
    qs = SxMaterialIssueRequest.objects.filter(is_demo=False, production_order=mo)
    for req in qs.select_related("stock_issue"):
        if req.status == "done":
            return True
        if req.stock_issue_id and getattr(req.stock_issue, "status", "") == DOC_STATUS_POSTED:
            return True
    return False


def check_issue_before_stat(*, mo: SxProductionOrder) -> GateResult:
    mode = gate_mode("SX_GATE_REQUIRE_ISSUE_BEFORE_STAT", MODE_BLOCK)
    if mode == MODE_OFF:
        return GateResult(ok=True, mode=mode, code="issue_before_stat")
    ok = _has_posted_material_issue(mo=mo)
    return GateResult(
        ok=ok,
        mode=mode,
        code="issue_before_stat",
        message=(
            f"Lệnh {mo.code} chưa có phiếu xuất nguyên phụ liệu đã ghi sổ — "
            "duyệt yêu cầu xuất trước khi xác nhận thống kê sản xuất."
            if not ok
            else ""
        ),
    )


def _has_qc_pass(*, mo: SxProductionOrder) -> bool:
    return SxQcInspection.objects.filter(
        is_demo=False,
        result=SxQcInspection.RESULT_PASS,
        qc_request__production_order=mo,
        qc_request__is_demo=False,
    ).exists()


def check_open_qc_alert_before_fg(*, mo: SxProductionOrder) -> GateResult:
    mode = gate_mode("SX_GATE_OPEN_QC_ALERT_BEFORE_FG", MODE_BLOCK)
    if mode == MODE_OFF:
        return GateResult(ok=True, mode=mode, code="open_qc_alert_before_fg")
    open_alert = SxQcAlert.objects.filter(
        production_order=mo, status=SxQcAlert.STATUS_OPEN, is_demo=False
    ).exists()
    return GateResult(
        ok=not open_alert,
        mode=mode,
        code="open_qc_alert_before_fg",
        message=(
            f"Lệnh {mo.code} còn cảnh báo chất lượng đang mở — xử lý trước khi nhập thành phẩm."
            if open_alert
            else ""
        ),
    )


def check_qc_pass_before_fg(*, mo: SxProductionOrder) -> GateResult:
    mode = gate_mode("SX_GATE_REQUIRE_QC_PASS_BEFORE_FG", MODE_BLOCK)
    if mode == MODE_OFF:
        return GateResult(ok=True, mode=mode, code="qc_pass_before_fg")
    ok = _has_qc_pass(mo=mo)
    return GateResult(
        ok=ok,
        mode=mode,
        code="qc_pass_before_fg",
        message=(
            f"Lệnh {mo.code} chưa có phiếu kiểm tra Đạt — "
            "hoàn tất kiểm tra chất lượng trước khi tạo yêu cầu nhập thành phẩm."
            if not ok
            else ""
        ),
    )


def check_stat_before_fg(*, mo: SxProductionOrder) -> GateResult:
    mode = gate_mode("SX_GATE_REQUIRE_STAT_BEFORE_FG", MODE_BLOCK)
    if mode == MODE_OFF:
        return GateResult(ok=True, mode=mode, code="stat_before_fg")
    ok = SxProductionStat.objects.filter(
        is_demo=False,
        production_order=mo,
        status=SxProductionStat.STATUS_CONFIRMED,
    ).exists()
    return GateResult(
        ok=ok,
        mode=mode,
        code="stat_before_fg",
        message=(
            f"Lệnh {mo.code} chưa có thống kê sản xuất đã xác nhận."
            if not ok
            else ""
        ),
    )


def _has_confirmed_packing(*, mo: SxProductionOrder) -> bool:
    return SxPackingRecord.objects.filter(
        is_demo=False,
        production_order=mo,
        status=SxPackingRecord.STATUS_CONFIRMED,
    ).exists()


def check_packing_before_done(*, mo: SxProductionOrder) -> GateResult:
    mode = gate_mode("SX_GATE_PACKING_BEFORE_DONE", MODE_OFF)
    if mode == MODE_OFF:
        return GateResult(ok=True, mode=mode, code="packing_before_done")
    ok = _has_confirmed_packing(mo=mo)
    return GateResult(
        ok=ok,
        mode=mode,
        code="packing_before_done",
        message=(
            f"Lệnh {mo.code} chưa có phiếu đóng gói đã xác nhận — "
            "cần đóng gói trước khi hoàn thành lệnh."
            if not ok
            else ""
        ),
    )
