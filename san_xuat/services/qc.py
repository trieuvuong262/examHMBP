from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from san_xuat.hub_models import (
    SxProductionStat,
    SxQcAlert,
    SxQcCriteria,
    SxQcDefect,
    SxQcInspection,
    SxQcInspectionCriteriaLine,
    SxQcInspectionDefectLine,
    SxQcRequest,
    SxQcSamplingMethod,
    SxQcStandardSet,
)

from san_xuat.services.sx_settings import sx_prefix


DEFAULT_TOLERANCE_PCT = Decimal("5")


def _default_tolerance() -> Decimal:
    from san_xuat.services.sx_settings import sx_decimal

    return sx_decimal("default_defect_tolerance_pct", DEFAULT_TOLERANCE_PCT)


class QcError(Exception):
    pass


def _next_code(prefix: str, model, *, field: str = "code") -> str:
    year = timezone.localdate().year
    base = f"{prefix}-{year}-"
    latest = (
        model.objects.filter(**{f"{field}__startswith": base})
        .order_by("-id")
        .values_list(field, flat=True)
        .first()
    )
    if not latest:
        return f"{base}0001"
    try:
        seq = int(latest.rsplit("-", 1)[-1]) + 1
    except ValueError:
        seq = model.objects.filter(**{f"{field}__startswith": base}).count() + 1
    return f"{base}{seq:04d}"


def _code(kind: str, model, *, code: str | None = None, field: str = "code"):
    raw = (code or "").strip()
    if raw:
        return raw
    return _next_code(sx_prefix(kind), model, field=field)


@dataclass(frozen=True)
class SampleResult:
    required_qty: Decimal
    max_defect_allowed: Decimal


@dataclass(frozen=True)
class StatQcLinkResult:
    qc_request: SxQcRequest | None
    alert: SxQcAlert | None


def compute_defect_rate(*, qty_good: Decimal, qty_defect: Decimal) -> Decimal:
    good = qty_good or Decimal("0")
    defect = qty_defect or Decimal("0")
    total = good + defect
    if total <= 0:
        return Decimal("0")
    return ((defect / total) * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def resolve_tolerance(*, product_code: str, stage_name: str = "") -> Decimal:
    qs = SxQcStandardSet.objects.filter(is_demo=False, is_active=True)
    stage = (stage_name or "").strip()
    product = (product_code or "").strip()

    candidates = []
    if product and stage:
        candidates.append(qs.filter(product_code=product, stage_name=stage))
    if product:
        candidates.append(qs.filter(product_code=product, stage_name=""))
    candidates.append(qs.filter(product_code=""))

    for candidate in candidates:
        standard = candidate.order_by("-id").first()
        if standard and standard.defect_tolerance_pct is not None:
            return standard.defect_tolerance_pct
    return _default_tolerance()


def compute_sample_qty(method: SxQcSamplingMethod | None, production_qty: Decimal) -> SampleResult:
    qty = production_qty or Decimal("0")
    if qty <= 0:
        return SampleResult(required_qty=Decimal("0"), max_defect_allowed=Decimal("0"))
    if not method:
        from san_xuat.services.sx_settings import sx_int

        required = Decimal(str(sx_int("default_sample_qty", 5, min_v=1, max_v=9999)))
    elif (method.method_type or "").strip() == "percent":
        pct = method.sample_value or Decimal("0")
        required = ((qty * pct) / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    else:
        required = (method.sample_value or Decimal("0")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if required <= 0:
        required = Decimal("1")
    max_defect = Decimal("0")
    return SampleResult(required_qty=required, max_defect_allowed=max_defect)


@transaction.atomic
def create_request_from_stat(
    *,
    stat_id: int,
    code: str | None = None,
    auto: bool = False,
) -> SxQcRequest:
    stat = SxProductionStat.objects.select_for_update().select_related("production_order").get(pk=stat_id)
    mo = stat.production_order
    if not mo:
        raise QcError("TKSX không gắn LSX.")

    existing = (
        SxQcRequest.objects.filter(production_stat=stat, is_demo=False)
        .exclude(status="cancelled")
        .order_by("-id")
        .first()
    )
    if existing:
        return existing

    qty = stat.qty_good or stat.qty_defect or Decimal("0")
    if qty <= 0:
        raise QcError("TKSX không có SL đạt/lỗi để sinh YCKT.")

    qc_req = SxQcRequest.objects.create(
        code=_code("qc_req", SxQcRequest, code=code),
        production_order=mo,
        production_stat=stat,
        product_code=mo.product_code,
        product_name=mo.product_name,
        stage_name=(stat.process_name or "").strip(),
        qty=qty,
        size_label=(stat.size_label or "").strip(),
        sku_code=(stat.sku_code or "").strip(),
        color_label=(stat.color_label or "").strip(),
        request_date=timezone.localdate(),
        status="open",
        notes=f"Tự sinh từ TKSX {stat.code}" if auto else "",
        is_demo=False,
    )
    return qc_req


@transaction.atomic
def maybe_create_defect_alert(*, stat: SxProductionStat) -> SxQcAlert | None:
    mo = stat.production_order
    if not mo:
        return None

    tolerance = resolve_tolerance(product_code=mo.product_code, stage_name=stat.process_name or "")
    rate = compute_defect_rate(qty_good=stat.qty_good, qty_defect=stat.qty_defect)
    if rate <= tolerance:
        return None

    existing = (
        SxQcAlert.objects.filter(
            production_stat=stat,
            alert_type=SxQcAlert.TYPE_DEFECT_RATE,
            status=SxQcAlert.STATUS_OPEN,
            is_demo=False,
        )
        .order_by("-id")
        .first()
    )
    if existing:
        return existing

    message = (
        f"Tỷ lệ lỗi {rate}% vượt ngưỡng {tolerance}% "
        f"tại công đoạn {stat.process_name or '—'} (TKSX {stat.code})."
    )
    return SxQcAlert.objects.create(
        code=_code("qc_alert", SxQcAlert),
        alert_type=SxQcAlert.TYPE_DEFECT_RATE,
        production_order=mo,
        production_stat=stat,
        process_name=(stat.process_name or "").strip(),
        defect_rate=rate,
        tolerance_limit=tolerance,
        qty_good=stat.qty_good or Decimal("0"),
        qty_defect=stat.qty_defect or Decimal("0"),
        message=message,
        status=SxQcAlert.STATUS_OPEN,
        is_demo=False,
    )


@transaction.atomic
def process_stat_qc_link(*, stat_id: int) -> StatQcLinkResult:
    from san_xuat.services.sx_settings import sx_bool

    stat = SxProductionStat.objects.select_related("production_order").get(pk=stat_id)
    if stat.status != SxProductionStat.STATUS_CONFIRMED:
        raise QcError("Chỉ nối QC sau khi TKSX đã xác nhận.")

    qc_request = None
    if sx_bool("auto_create_qc_from_stat", True):
        try:
            qc_request = create_request_from_stat(stat_id=stat.pk, auto=True)
        except QcError:
            pass

    alert = None
    if sx_bool("auto_create_defect_alert", True):
        alert = maybe_create_defect_alert(stat=stat)
    return StatQcLinkResult(qc_request=qc_request, alert=alert)


def _criteria_for_standard(standard: SxQcStandardSet | None) -> list[SxQcCriteria]:
    if standard:
        linked = list(
            SxQcCriteria.objects.filter(
                standard_links__standard_set=standard,
                is_demo=False,
                is_active=True,
            )
            .order_by("standard_links__sort_order", "code")
        )
        if linked:
            return linked
    return list(
        SxQcCriteria.objects.filter(is_demo=False, is_active=True).order_by("code")[:15]
    )


@transaction.atomic
def seed_inspection_criteria_lines(*, inspection: SxQcInspection) -> list[SxQcInspectionCriteriaLine]:
    if inspection.criteria_lines.exists():
        return list(inspection.criteria_lines.select_related("criteria").all())

    criteria_list = _criteria_for_standard(inspection.standard_set)
    lines = [
        SxQcInspectionCriteriaLine(inspection=inspection, criteria=criteria)
        for criteria in criteria_list
    ]
    if lines:
        SxQcInspectionCriteriaLine.objects.bulk_create(lines)
    return list(inspection.criteria_lines.select_related("criteria").all())


@dataclass(frozen=True)
class CriteriaLineInput:
    line_id: int
    is_pass: bool | None = None
    value_text: str = ""
    value_number: Decimal | None = None
    notes: str = ""


@dataclass(frozen=True)
class DefectLineInput:
    defect_id: int
    qty: Decimal = Decimal("0")
    notes: str = ""


@transaction.atomic
def save_inspection_detail_lines(
    *,
    inspection_id: int,
    criteria_lines: list[CriteriaLineInput] | None = None,
    defect_lines: list[DefectLineInput] | None = None,
) -> SxQcInspection:
    inspection = SxQcInspection.objects.select_for_update().get(pk=inspection_id)
    if inspection.status == "done":
        raise QcError("Phiếu kiểm tra đã chốt, không thể sửa chi tiết.")

    seed_inspection_criteria_lines(inspection=inspection)

    if criteria_lines:
        line_map = {
            line.pk: line
            for line in inspection.criteria_lines.select_for_update().all()
        }
        for item in criteria_lines:
            line = line_map.get(item.line_id)
            if not line:
                continue
            line.is_pass = item.is_pass
            line.value_text = (item.value_text or "").strip()
            line.value_number = item.value_number
            line.notes = (item.notes or "").strip()
            line.save(update_fields=["is_pass", "value_text", "value_number", "notes"])

    if defect_lines is not None:
        inspection.defect_lines.all().delete()
        defect_ids = [item.defect_id for item in defect_lines if item.qty and item.qty > 0]
        defects = {
            defect.pk: defect
            for defect in SxQcDefect.objects.filter(pk__in=defect_ids, is_demo=False, is_active=True)
        }
        create_lines = []
        for item in defect_lines:
            if not item.qty or item.qty <= 0:
                continue
            defect = defects.get(item.defect_id)
            if not defect:
                raise QcError(f"Lỗi QC không hợp lệ: id={item.defect_id}")
            create_lines.append(
                SxQcInspectionDefectLine(
                    inspection=inspection,
                    defect=defect,
                    qty=item.qty,
                    notes=(item.notes or "").strip(),
                )
            )
        if create_lines:
            SxQcInspectionDefectLine.objects.bulk_create(create_lines)

    return inspection


@transaction.atomic
def maybe_create_inspection_fail_alert(*, inspection: SxQcInspection) -> SxQcAlert | None:
    if inspection.result != SxQcInspection.RESULT_FAIL:
        return None

    qc_req = inspection.qc_request
    mo = getattr(qc_req, "production_order", None) if qc_req else None
    if not mo:
        return None

    existing = (
        SxQcAlert.objects.filter(
            qc_inspection=inspection,
            alert_type=SxQcAlert.TYPE_QC_FAIL,
            is_demo=False,
        )
        .order_by("-id")
        .first()
    )
    if existing:
        return existing

    sample_qty = inspection.qty_sample or Decimal("0")
    fail_qty = inspection.qty_fail or Decimal("0")
    rate = Decimal("0")
    if sample_qty > 0:
        rate = ((fail_qty / sample_qty) * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    tolerance = resolve_tolerance(
        product_code=mo.product_code,
        stage_name=(qc_req.stage_name if qc_req else "") or "",
    )
    message = (
        f"PKT {inspection.code} không đạt: {fail_qty}/{sample_qty} mẫu lỗi "
        f"({rate}%). Cần xử lý tại LSX {mo.code}."
    )
    return SxQcAlert.objects.create(
        code=_code("qc_alert", SxQcAlert),
        alert_type=SxQcAlert.TYPE_QC_FAIL,
        production_order=mo,
        production_stat=getattr(qc_req, "production_stat", None) if qc_req else None,
        qc_request=qc_req,
        qc_inspection=inspection,
        process_name=(qc_req.stage_name if qc_req else "") or "",
        defect_rate=rate,
        tolerance_limit=tolerance,
        qty_good=inspection.qty_pass or Decimal("0"),
        qty_defect=inspection.qty_fail or Decimal("0"),
        message=message,
        status=SxQcAlert.STATUS_OPEN,
        is_demo=False,
    )


@transaction.atomic
def acknowledge_alert(*, alert_id: int) -> SxQcAlert:
    alert = SxQcAlert.objects.select_for_update().get(pk=alert_id)
    if alert.status == SxQcAlert.STATUS_CLOSED:
        raise QcError("Cảnh báo đã đóng.")
    alert.status = SxQcAlert.STATUS_ACK
    alert.save(update_fields=["status"])
    return alert


@transaction.atomic
def create_inspection_from_request(
    *,
    request_id: int,
    standard_id: int | None = None,
    code: str | None = None,
    inspected_at=None,
    notes: str = "",
) -> SxQcInspection:
    qc_req = SxQcRequest.objects.select_for_update().get(pk=request_id)
    if qc_req.status == "cancelled":
        raise QcError("YCKT đã hủy, không thể tạo phiếu kiểm tra.")

    standard = None
    if standard_id:
        standard = SxQcStandardSet.objects.filter(pk=standard_id, is_demo=False).first()
        if not standard:
            raise QcError("Bộ tiêu chuẩn không tồn tại.")
    elif qc_req.product_code:
        standard = (
            SxQcStandardSet.objects.filter(is_demo=False, is_active=True, product_code__in=[qc_req.product_code, ""])
            .order_by("-product_code")
            .first()
        )

    sample = compute_sample_qty(getattr(standard, "sampling_method", None), qc_req.qty or Decimal("0"))
    inspection = SxQcInspection.objects.create(
        code=_code("qc_sheet", SxQcInspection, code=code),
        qc_request=qc_req,
        standard_set=standard,
        inspected_at=inspected_at or timezone.localdate(),
        qty_sample=sample.required_qty,
        qty_pass=Decimal("0"),
        qty_fail=Decimal("0"),
        result=SxQcInspection.RESULT_PENDING,
        status="draft",
        notes=notes or "",
        is_demo=False,
    )
    if qc_req.status == "open":
        qc_req.status = "in_progress"
        qc_req.save(update_fields=["status"])
    seed_inspection_criteria_lines(inspection=inspection)
    return inspection


@transaction.atomic
def finalize_inspection(
    *,
    inspection_id: int,
    qty_pass: Decimal | None = None,
    qty_fail: Decimal | None = None,
    notes: str = "",
    criteria_lines: list[CriteriaLineInput] | None = None,
    defect_lines: list[DefectLineInput] | None = None,
) -> SxQcInspection:
    inspection = save_inspection_detail_lines(
        inspection_id=inspection_id,
        criteria_lines=criteria_lines,
        defect_lines=defect_lines,
    )
    inspection = SxQcInspection.objects.select_for_update().get(pk=inspection.pk)
    if inspection.status == "done":
        raise QcError("Phiếu kiểm tra đã chốt.")

    sample_qty = inspection.qty_sample or Decimal("0")
    defect_total = sum(
        (line.qty or Decimal("0") for line in inspection.defect_lines.all()),
        Decimal("0"),
    )
    if defect_lines is not None and defect_total > 0:
        fail_qty = defect_total
    else:
        fail_qty = qty_fail or Decimal("0")

    if fail_qty < 0:
        raise QcError("SL lỗi không được âm.")
    if sample_qty > 0 and fail_qty > sample_qty:
        raise QcError("Tổng SL lỗi vượt quá SL mẫu.")

    if qty_pass is not None:
        pass_qty = qty_pass
    elif sample_qty > 0:
        pass_qty = sample_qty - fail_qty
    else:
        pass_qty = Decimal("0")

    if pass_qty < 0:
        raise QcError("SL đạt không được âm.")
    if sample_qty > 0 and (pass_qty + fail_qty) > sample_qty:
        raise QcError("Tổng SL đạt + lỗi vượt quá SL mẫu.")

    failed_criteria = inspection.criteria_lines.filter(is_pass=False).exists()
    inspection.qty_pass = pass_qty
    inspection.qty_fail = fail_qty
    inspection.notes = notes or inspection.notes
    inspection.result = (
        SxQcInspection.RESULT_FAIL
        if fail_qty > 0 or failed_criteria
        else SxQcInspection.RESULT_PASS
    )
    inspection.status = "done"
    inspection.save(update_fields=["qty_pass", "qty_fail", "notes", "result", "status"])

    qc_req = inspection.qc_request
    if qc_req:
        qc_req.status = "done"
        qc_req.save(update_fields=["status"])

    if inspection.result == SxQcInspection.RESULT_FAIL:
        maybe_create_inspection_fail_alert(inspection=inspection)

    return inspection
