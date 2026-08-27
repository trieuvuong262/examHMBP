from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from san_xuat.hub_models import (
    SxProductionOrder,
    SxProductionStat,
    SxQcAlert,
    SxQcCriteria,
    SxQcCriteriaGroup,
    SxQcDefect,
    SxQcInspection,
    SxQcInspectionCriteriaLine,
    SxQcInspectionDefectLine,
    SxQcInspectionTeamResult,
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
    """Sinh mã {prefix}-{year}-{seq:04d} — lấy max số thứ tự số, bỏ qua mã không chuẩn."""
    year = timezone.localdate().year
    base = f"{prefix}-{year}-"
    seq = 0
    for raw in model.objects.filter(**{f"{field}__startswith": base}).values_list(field, flat=True):
        suffix = (raw or "").rsplit("-", 1)[-1]
        if suffix.isdigit():
            seq = max(seq, int(suffix))
    for _ in range(10000):
        seq += 1
        candidate = f"{base}{seq:04d}"
        if not model.objects.filter(**{field: candidate}).exists():
            return candidate
    raise QcError(f"Không sinh được mã mới với tiền tố {base}.")


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
    max_defect = Decimal("0")
    method_type = (getattr(method, "method_type", "") or "").strip()

    if not method:
        from san_xuat.services.sx_settings import sx_int

        required = Decimal(str(sx_int("default_sample_qty", 5, min_v=1, max_v=9999)))
    elif method_type == SxQcSamplingMethod.TYPE_AQL:
        from san_xuat.services.aql import AqlError, aql_sample_plan

        try:
            plan = aql_sample_plan(
                lot_size=qty,
                aql=method.aql_level,
                inspection_level=method.inspection_level,
            )
        except AqlError:
            required = Decimal("1")
        else:
            required = Decimal(plan.sample_size)
            max_defect = Decimal(plan.accept)
    elif method_type == SxQcSamplingMethod.TYPE_PERCENT:
        pct = method.sample_value or Decimal("0")
        required = ((qty * pct) / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    else:
        required = (method.sample_value or Decimal("0")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if required <= 0:
        required = Decimal("1")
    if required > qty:
        required = qty.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return SampleResult(required_qty=required, max_defect_allowed=max_defect)


def aql_plan_for_request(qc_request: SxQcRequest) -> object | None:
    """Kế hoạch AQL của một YCKT — dùng để hiện rõ mẫu/Ac trên phiếu kiểm tra."""
    standard = (
        SxQcStandardSet.objects.filter(
            is_demo=False,
            is_active=True,
            product_code__in=[qc_request.product_code or "", ""],
        )
        .order_by("-product_code")
        .first()
    )
    method = getattr(standard, "sampling_method", None)
    if not method or (method.method_type or "").strip() != SxQcSamplingMethod.TYPE_AQL:
        return None
    from san_xuat.services.aql import AqlError, aql_sample_plan

    try:
        return aql_sample_plan(
            lot_size=qc_request.qty or Decimal("0"),
            aql=method.aql_level,
            inspection_level=method.inspection_level,
        )
    except AqlError:
        return None


def stage_requires_inspection(*, product_code: str, stage_name: str) -> bool:
    """Công đoạn có được đánh dấu QC trọng yếu trên routing IE hay không."""
    stage = (stage_name or "").strip()
    code = (product_code or "").strip()
    if not stage or not code:
        return False
    from san_xuat.services.scheduling import product_routing

    routing = product_routing(code)
    target = stage.casefold()
    for step in routing.steps:
        if (step.process_name or "").strip().casefold() != target:
            continue
        line = getattr(step, "source_line", None)
        if line is not None and getattr(line, "critical_qc", False):
            return True

    from san_xuat.ie_models import SxRouting, SxRoutingLine

    routing_ids = SxRouting.objects.filter(style_code__iexact=code).values_list("pk", flat=True)
    if not routing_ids:
        return False
    return SxRoutingLine.objects.filter(
        routing_id__in=list(routing_ids),
        critical_qc=True,
    ).filter(
        Q(op_name_vi__iexact=stage) | Q(op_code__iexact=stage),
    ).exists()


QC_STATUS_IDLE = "idle"
QC_STATUS_OPEN = "open"
QC_STATUS_PASS = "pass"
QC_STATUS_FAIL = "fail"
QC_STATUS_SKIP = "skip"

QC_STATUS_LABELS = {
    QC_STATUS_IDLE: "Chờ",
    QC_STATUS_OPEN: "Đang kiểm",
    QC_STATUS_PASS: "Đạt",
    QC_STATUS_FAIL: "Không đạt",
    QC_STATUS_SKIP: "Không QC",
}

QC_PROGRESS_DONE = frozenset({QC_STATUS_PASS, QC_STATUS_FAIL})


@dataclass(frozen=True)
class QcTeam:
    slug: str
    label: str
    work_center_id: int | None = None
    work_center_code: str = ""


def _team_meta(slug: str) -> dict:
    from san_xuat.services.progress_template import team_by_slug

    return team_by_slug(slug) or {"slug": slug, "label": slug, "work_center_code": ""}


def resolve_team_slug_from_routing_line(line) -> str | None:
    from san_xuat.services.progress_template import (
        team_slug_for_process_label,
        team_slug_for_work_center_code,
    )

    wc = getattr(line, "work_center", None)
    code = (getattr(wc, "code", None) or getattr(line, "work_center_code", "") or "").strip()
    slug = team_slug_for_work_center_code(code)
    if slug:
        return slug
    group = (getattr(line, "group_code", "") or "").strip()
    slug = team_slug_for_work_center_code(group)
    if slug:
        return slug
    name = (
        getattr(line, "op_name_vi", None)
        or getattr(line, "process_name", None)
        or ""
    )
    slug = team_slug_for_process_label(name)
    if slug:
        return slug
    team_label = ""
    if wc is not None:
        team_label = (getattr(wc, "team_label", None) or getattr(wc, "name", None) or "") or ""
    return team_slug_for_work_center_code(team_label) or team_slug_for_process_label(team_label)


def resolve_team_slug_from_process(process_name: str, *, team_label: str = "") -> str | None:
    from san_xuat.services.progress_template import (
        team_slug_for_process_label,
        team_slug_for_work_center_code,
    )

    slug = team_slug_for_process_label(process_name or "")
    if slug:
        return slug
    slug = team_slug_for_work_center_code(process_name or "")
    if slug:
        return slug
    return team_slug_for_work_center_code(team_label or "") or team_slug_for_process_label(team_label or "")


def _order_for_mo(mo: SxProductionOrder | None):
    if mo is None:
        return None
    if getattr(mo, "sales_order_id", None):
        return mo.sales_order
    return None


def ob_routing_lines(*, mo: SxProductionOrder | None = None, order=None) -> list:
    so = order or _order_for_mo(mo)
    if so is None:
        return []
    lines = []
    for sol in so.lines.all():
        rel = sol.routing_lines
        if hasattr(rel, "select_related"):
            lines.extend(list(rel.select_related("work_center").all()))
        else:
            lines.extend(list(rel.all()))
    return lines


def _qc_team_from_line(line) -> QcTeam | None:
    slug = resolve_team_slug_from_routing_line(line)
    if not slug:
        return None
    meta = _team_meta(slug)
    wc = getattr(line, "work_center", None)
    return QcTeam(
        slug=slug,
        label=meta.get("label") or slug,
        work_center_id=getattr(wc, "pk", None) or getattr(line, "work_center_id", None),
        work_center_code=(
            getattr(wc, "code", None)
            or getattr(line, "work_center_code", "")
            or meta.get("work_center_code")
            or ""
        ),
    )


def _ordered_qc_teams(seen: dict[str, QcTeam]) -> list[QcTeam]:
    from san_xuat.services.progress_template import TEAM_SLUGS

    out: list[QcTeam] = []
    for slug, _gk, _menu, _label in TEAM_SLUGS:
        team = seen.get(slug)
        if team:
            out.append(team)
    return out


def _collect_qc_teams(lines) -> dict[str, QcTeam]:
    seen: dict[str, QcTeam] = {}
    for line in lines or []:
        team = _qc_team_from_line(line)
        if team and team.slug not in seen:
            seen[team.slug] = team
    return seen


def _lsx_routing_lines(mo: SxProductionOrder | None) -> list:
    if mo is None:
        return []
    routing = getattr(mo, "routing", None)
    if routing is None:
        return []
    rel = routing.lines
    if hasattr(rel, "select_related"):
        return list(rel.select_related("work_center").all())
    return list(rel.all())


def _bom_process_steps(mo: SxProductionOrder | None) -> list:
    if mo is None:
        return []
    bom = getattr(mo, "bom_version", None)
    if bom is None:
        return []
    rel = bom.process_steps
    if hasattr(rel, "select_related"):
        return list(rel.select_related("work_center").all())
    return list(rel.all())


def ob_source_lines(*, mo: SxProductionOrder | None = None, order=None) -> list:
    """Công đoạn nguồn tổ: Ob đơn → Ob LSX → Bom. Rỗng = chưa xác định tổ."""
    lines = ob_routing_lines(mo=mo, order=order)
    if lines:
        return lines
    lines = _lsx_routing_lines(mo)
    if lines:
        return lines
    return _bom_process_steps(mo)


def ob_qc_teams(*, mo: SxProductionOrder | None = None, order=None) -> list[QcTeam]:
    """Tổ tham gia = tổ có mặt trên Ob đơn / Ob LSX / Bom. Không mặc định đủ 6 tổ."""
    return _ordered_qc_teams(_collect_qc_teams(ob_source_lines(mo=mo, order=order)))


def ob_team_options(*, mo: SxProductionOrder | None = None, order=None) -> list[dict]:
    """Choices tổ thuê GC: chỉ tổ có trên Ob của lệnh."""
    return [
        {'slug': t.slug, 'label': t.label, 'work_center_code': t.work_center_code or ''}
        for t in ob_qc_teams(mo=mo, order=order)
    ]


def team_output_qty_for_mo(mo: SxProductionOrder | None) -> dict[str, tuple[Decimal, Decimal]]:
    """Sản lượng tổ = lượng ra khỏi tổ (như tiến độ), không cộng dồn mọi công đoạn."""
    if mo is None:
        return {}
    from san_xuat.services.handover_status import build_mo_handover_row

    row = build_mo_handover_row(mo)
    return {
        cell.slug: (cell.done or Decimal("0"), Decimal("0"))
        for cell in row.cells
        if cell.slug
    }


def work_center_for_slug(slug: str):
    from san_xuat.hub_models import SxWorkCenter
    from san_xuat.services.progress_template import team_by_slug

    meta = team_by_slug(slug) or {}
    code = (meta.get("work_center_code") or "").strip()
    if not code:
        return None
    return SxWorkCenter.objects.filter(code__iexact=code).first()


def qc_status_map_for_mos(mos: list[SxProductionOrder]) -> dict[tuple[int, str], str]:
    """(mo_id, slug) → status. Một query cho nhiều lệnh."""
    mo_ids = [m.pk for m in mos if m is not None]
    if not mo_ids:
        return {}
    out: dict[tuple[int, str], str] = {}
    insp_rows = (
        SxQcInspection.objects.filter(
            is_demo=False,
            qc_request__production_order_id__in=mo_ids,
            qc_request__is_demo=False,
        )
        .exclude(qc_request__status="cancelled")
        .exclude(qc_request__team_slug="")
        .values_list("qc_request__production_order_id", "qc_request__team_slug", "result", "pk")
    )
    by_key: dict[tuple[int, str], list[tuple[str, int]]] = {}
    for mo_id, slug, result, pk in insp_rows:
        by_key.setdefault((mo_id, slug), []).append((result, pk))
    req_rows = (
        SxQcRequest.objects.filter(
            production_order_id__in=mo_ids,
            is_demo=False,
        )
        .exclude(status="cancelled")
        .exclude(team_slug="")
        .values_list("production_order_id", "team_slug", "status")
    )
    open_keys: set[tuple[int, str]] = set()
    for mo_id, slug, status in req_rows:
        if status not in {"done", "cancelled"}:
            open_keys.add((mo_id, slug))
    for key, rows in by_key.items():
        if any(r == SxQcInspection.RESULT_PASS for r, _pk in rows):
            out[key] = QC_STATUS_PASS
            continue
        latest = max(rows, key=lambda item: item[1])
        if latest[0] == SxQcInspection.RESULT_FAIL:
            out[key] = QC_STATUS_FAIL
        elif latest[0] == SxQcInspection.RESULT_PENDING or key in open_keys:
            out[key] = QC_STATUS_OPEN
        else:
            out[key] = QC_STATUS_IDLE
    for key in open_keys:
        out.setdefault(key, QC_STATUS_OPEN)

    team_rows = (
        SxQcInspectionTeamResult.objects.filter(
            inspection__is_demo=False,
            inspection__qc_request__production_order_id__in=mo_ids,
            inspection__qc_request__is_demo=False,
        )
        .exclude(inspection__qc_request__status="cancelled")
        .values_list("inspection__qc_request__production_order_id", "team_slug", "result")
    )
    for mo_id, slug, result in team_rows:
        if not slug:
            continue
        key = (mo_id, slug)
        if result == SxQcInspectionTeamResult.RESULT_PASS:
            out[key] = QC_STATUS_PASS
        elif result == SxQcInspectionTeamResult.RESULT_FAIL and out.get(key) != QC_STATUS_PASS:
            out[key] = QC_STATUS_FAIL
        elif result == SxQcInspectionTeamResult.RESULT_PENDING and key not in out:
            out[key] = QC_STATUS_OPEN
    return out


def team_qc_status(*, mo: SxProductionOrder, slug: str) -> str:
    return qc_status_map_for_mos([mo]).get((mo.pk, slug), QC_STATUS_IDLE)


def latest_qc_inspection_ids_for_mos(mos: list[SxProductionOrder]) -> dict[int, int]:
    """mo_id → phiếu kiểm tra mới nhất (để mở chi tiết từ Tiến độ QC)."""
    mo_ids = [m.pk for m in mos if m is not None]
    if not mo_ids:
        return {}
    rows = (
        SxQcInspection.objects.filter(
            is_demo=False,
            qc_request__production_order_id__in=mo_ids,
            qc_request__is_demo=False,
        )
        .exclude(qc_request__status="cancelled")
        .order_by("qc_request__production_order_id", "-pk")
        .values_list("qc_request__production_order_id", "pk")
    )
    out: dict[int, int] = {}
    for mo_id, pk in rows:
        out.setdefault(mo_id, pk)
    return out


def ob_qc_progress(*, mo: SxProductionOrder) -> tuple[int, int, list[str]]:
    """(số tổ đã QC Đạt, tổng tổ Ob, nhãn tổ còn thiếu)."""
    teams = ob_qc_teams(mo=mo)
    if not teams:
        return 0, 0, []
    status_map = qc_status_map_for_mos([mo])
    missing = [
        t.label
        for t in teams
        if status_map.get((mo.pk, t.slug)) != QC_STATUS_PASS
    ]
    total = len(teams)
    return total - len(missing), total, missing


def all_ob_teams_qc_passed(*, mo: SxProductionOrder) -> tuple[bool, list[str]]:
    """True nếu mọi tổ trên Ob đã QC Đạt. Trả thêm nhãn tổ còn thiếu."""
    passed, total, missing = ob_qc_progress(mo=mo)
    if total == 0:
        return True, []
    return passed == total, missing


def latest_qc_inspection(*, mo: SxProductionOrder) -> SxQcInspection | None:
    return (
        SxQcInspection.objects.filter(
            is_demo=False,
            qc_request__production_order=mo,
            qc_request__is_demo=False,
        )
        .exclude(qc_request__status="cancelled")
        .order_by("-pk")
        .first()
    )


def qc_ready_for_fg(*, mo: SxProductionOrder) -> tuple[bool, str]:
    """Nhập TP khi đủ tổ Đạt và phiếu đã chốt Đạt."""
    passed, total, missing = ob_qc_progress(mo=mo)
    if total == 0:
        return True, ""
    if missing:
        return False, (
            f"Chưa hoàn thành Kiểm tra sản phẩm ({passed}/{total}) — còn {', '.join(missing)}."
        )
    insp = latest_qc_inspection(mo=mo)
    if insp is None or insp.status != "done":
        return False, (
            f"Đã lưu đủ tổ ({passed}/{total}) nhưng chưa chốt phiếu kiểm tra."
        )
    if insp.result != SxQcInspection.RESULT_PASS:
        return False, "Phiếu kiểm tra đã chốt nhưng chưa Đạt — không được nhập thành phẩm."
    return True, ""


def latest_pass_inspection(*, mo: SxProductionOrder) -> SxQcInspection | None:
    return (
        SxQcInspection.objects.filter(
            is_demo=False,
            result=SxQcInspection.RESULT_PASS,
            qc_request__production_order=mo,
            qc_request__is_demo=False,
        )
        .order_by("-pk")
        .first()
    )


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
        if not (existing.team_slug or "").strip():
            slug = resolve_team_slug_from_process(
                (stat.process_name or "").strip(),
                team_label=getattr(stat, "team_label", "") or getattr(mo, "team_label", ""),
            ) or ""
            if slug:
                existing.team_slug = slug
                if not existing.work_center_id:
                    existing.work_center = work_center_for_slug(slug)
                existing.save(update_fields=["team_slug", "work_center"])
        return existing

    qty = stat.qty_good or stat.qty_defect or Decimal("0")
    if qty <= 0:
        raise QcError("TKSX không có SL đạt/lỗi để sinh YCKT.")

    process_name = (stat.process_name or "").strip()
    team_slug = resolve_team_slug_from_process(
        process_name,
        team_label=getattr(stat, "team_label", "") or getattr(mo, "team_label", ""),
    ) or ""
    wc = work_center_for_slug(team_slug) if team_slug else None

    qc_req = SxQcRequest.objects.create(
        code=_code("qc_req", SxQcRequest, code=code),
        production_order=mo,
        production_stat=stat,
        product_code=mo.product_code,
        product_name=mo.product_name,
        stage_name=process_name,
        team_slug=team_slug,
        work_center=wc,
        qty=qty,
        sku_id=stat.sku_id,
        size_label=(stat.size_label or "").strip(),
        sku_code=(stat.sku_code or "").strip(),
        color_label=(stat.color_label or "").strip(),
        color_code=(stat.color_code or "").strip(),
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

    # Tổ có trên Ob luôn sinh YCKT; QC trọng yếu / thiết lập tự sinh vẫn giữ.
    mo = stat.production_order
    process_name = stat.process_name or ""
    team_slug = resolve_team_slug_from_process(
        process_name,
        team_label=getattr(stat, "team_label", "") or getattr(mo, "team_label", "") if mo else "",
    ) or ""
    on_ob = False
    if mo and team_slug:
        on_ob = any(t.slug == team_slug for t in ob_qc_teams(mo=mo))
    critical = stage_requires_inspection(
        product_code=getattr(mo, "product_code", "") or "",
        stage_name=process_name,
    )

    qc_request = None
    if on_ob or critical or sx_bool("auto_create_qc_from_stat", True):
        try:
            qc_request = create_request_from_stat(stat_id=stat.pk, auto=True)
        except QcError:
            pass

    alert = None
    if sx_bool("auto_create_defect_alert", True):
        alert = maybe_create_defect_alert(stat=stat)
    return StatQcLinkResult(qc_request=qc_request, alert=alert)


DEFAULT_TEAM_CRITERIA: tuple[tuple[str, str, tuple[tuple[str, str], ...]], ...] = (
    (
        "cat",
        "Cắt",
        (
            ("TC-CAT-01", "Đúng số lượng / khổ chi tiết theo rập"),
            ("TC-CAT-02", "Không sờn mép, lệch sợi, cháy dao"),
            ("TC-CAT-03", "Đối xứng thân trước/sau, tay, cổ"),
            ("TC-CAT-04", "Tem size / ký hiệu chi tiết đúng"),
        ),
    ),
    (
        "inep",
        "In - Ép",
        (
            ("TC-INEP-01", "Vị trí in / ép đúng rập"),
            ("TC-INEP-02", "Màu sắc, độ bám, không bong"),
            ("TC-INEP-03", "Không lem, nứt, bóng hồ"),
            ("TC-INEP-04", "Căn giữa, không lệch / đảo mặt"),
        ),
    ),
    (
        "theu",
        "Thêu",
        (
            ("TC-THEU-01", "Vị trí thêu đúng rập"),
            ("TC-THEU-02", "Mật độ mũi đều, không sùi chỉ"),
            ("TC-THEU-03", "Đúng màu chỉ theo spec"),
            ("TC-THEU-04", "Không nhăn vải quanh vùng thêu"),
        ),
    ),
    (
        "may",
        "May",
        (
            ("TC-MAY-01", "Đường may thẳng, không gãy / xô chỉ"),
            ("TC-MAY-02", "Đúng seam allowance, không lệch mép"),
            ("TC-MAY-03", "Không skip stitch, lỗ kim to"),
            ("TC-MAY-04", "Khóa / nút / tag đúng vị trí"),
        ),
    ),
    (
        "ht",
        "Ủi - Gấp xếp",
        (
            ("TC-HT-01", "Ủi phẳng, không bóng ủi / cháy"),
            ("TC-HT-02", "Gấp đúng form, thông số packing"),
            ("TC-HT-03", "Sạch chỉ thừa, không dính bẩn"),
            ("TC-HT-04", "Size / combo xếp đúng"),
        ),
    ),
    (
        "gh",
        "Giao hàng thành phẩm",
        (
            ("TC-GH-01", "Đúng mã, màu, size so với đơn"),
            ("TC-GH-02", "Bao bì, nhãn hàng đầy đủ"),
            ("TC-GH-03", "Số lượng khớp packing list"),
            ("TC-GH-04", "Ngoại quan thành phẩm đạt"),
        ),
    ),
)


def seed_default_team_qc_criteria() -> int:
    """Tạo nhóm + tiêu chuẩn mặc định theo 6 tổ Ob (idempotent theo mã)."""
    created = 0
    for slug, label, items in DEFAULT_TEAM_CRITERIA:
        group, _ = SxQcCriteriaGroup.objects.get_or_create(
            code=f"QC-{slug.upper()}",
            defaults={
                "name": f"Tiêu chuẩn {label}",
                "is_active": True,
                "is_demo": False,
            },
        )
        for code, name in items:
            obj, was_created = SxQcCriteria.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "group": group,
                    "kind": SxQcCriteria.KIND_QUALITATIVE,
                    "team_slug": slug,
                    "is_active": True,
                    "is_demo": False,
                },
            )
            if was_created:
                created += 1
            elif not (obj.team_slug or "").strip():
                obj.team_slug = slug
                obj.save(update_fields=["team_slug"])
    return created


def _criteria_for_team(
    *,
    standard: SxQcStandardSet | None,
    team_slug: str = "",
) -> list[SxQcCriteria]:
    """Tiêu chuẩn hiện trên tab tổ: ưu tiên tiêu chí gán đúng slug."""
    slug = (team_slug or "").strip().lower()
    base = SxQcCriteria.objects.filter(is_demo=False, is_active=True)
    if slug:
        team_qs = base.filter(team_slug=slug)
        if standard:
            linked = list(
                team_qs.filter(standard_links__standard_set=standard).order_by(
                    "standard_links__sort_order", "code"
                )
            )
            if linked:
                return linked
        team_list = list(team_qs.order_by("code"))
        if team_list:
            return team_list
        return []
    if standard:
        linked = list(
            base.filter(standard_links__standard_set=standard, team_slug="").order_by(
                "standard_links__sort_order", "code"
            )
        )
        if linked:
            return linked
    return list(base.filter(team_slug="").order_by("code")[:15])


def _sync_inspection_team_criteria(inspection: SxQcInspection, teams: list[QcTeam]) -> None:
    """Gắn đúng tiêu chuẩn từng tổ; phiếu chưa nhập thì bỏ dòng clone cũ."""
    slugs = [t.slug for t in teams] or [""]
    if teams:
        existing_results = set(inspection.team_results.values_list("team_slug", flat=True))
        missing = [
            SxQcInspectionTeamResult(inspection=inspection, team_slug=t.slug)
            for t in teams
            if t.slug not in existing_results
        ]
        if missing:
            SxQcInspectionTeamResult.objects.bulk_create(missing, ignore_conflicts=True)
        # SL mặc định chỉ hiện trên form; chưa lưu tổ thì không ghi Đạt vào Tiến độ QC.
        inspection.team_results.filter(
            result=SxQcInspectionTeamResult.RESULT_PENDING,
        ).update(qty_pass=Decimal("0"), qty_fail=Decimal("0"))
        pending_slugs = list(
            inspection.team_results.filter(
                result=SxQcInspectionTeamResult.RESULT_PENDING,
            ).values_list("team_slug", flat=True)
        )
        if pending_slugs:
            inspection.criteria_lines.filter(team_slug__in=pending_slugs).update(is_pass=None)

    desired: list[tuple[str, SxQcCriteria]] = []
    for slug in slugs:
        for criteria in _criteria_for_team(standard=inspection.standard_set, team_slug=slug):
            desired.append((slug, criteria))
    desired_keys = {(slug, criteria.pk) for slug, criteria in desired}
    existing = {
        (line.team_slug or "", line.criteria_id): line
        for line in inspection.criteria_lines.all()
    }
    to_create = [
        SxQcInspectionCriteriaLine(
            inspection=inspection,
            criteria=criteria,
            team_slug=slug,
        )
        for slug, criteria in desired
        if (slug, criteria.pk) not in existing
    ]
    if to_create:
        SxQcInspectionCriteriaLine.objects.bulk_create(to_create)

    untouched = not inspection.criteria_lines.exclude(is_pass=None).exists()
    if untouched and desired_keys:
        stale_ids = [
            line.pk for key, line in existing.items() if key not in desired_keys
        ]
        if stale_ids:
            SxQcInspectionCriteriaLine.objects.filter(pk__in=stale_ids).delete()
    elif teams:
        inspection.criteria_lines.filter(team_slug="").delete()


@transaction.atomic
def seed_inspection_criteria_lines(*, inspection: SxQcInspection) -> list[SxQcInspectionCriteriaLine]:
    mo = getattr(getattr(inspection, "qc_request", None), "production_order", None)
    teams = ob_qc_teams(mo=mo) if mo else []
    _sync_inspection_team_criteria(inspection, teams)
    return list(inspection.criteria_lines.select_related("criteria").all())


@dataclass(frozen=True)
class CriteriaLineInput:
    line_id: int
    is_pass: bool | None = None
    value_text: str = ""
    value_number: Decimal | None = None
    notes: str = ""


@dataclass(frozen=True)
class TeamQtyInput:
    slug: str
    qty_pass: Decimal = Decimal("0")
    qty_fail: Decimal = Decimal("0")


def _team_result_status(*, qty_pass: Decimal, qty_fail: Decimal, failed_criteria: bool) -> str:
    if failed_criteria:
        return SxQcInspectionTeamResult.RESULT_FAIL
    if (qty_pass or Decimal("0")) > 0:
        return SxQcInspectionTeamResult.RESULT_PASS
    if (qty_fail or Decimal("0")) > 0:
        return SxQcInspectionTeamResult.RESULT_FAIL
    return SxQcInspectionTeamResult.RESULT_PENDING


@transaction.atomic
def save_inspection_team_results(
    *,
    inspection_id: int,
    team_qty: list[TeamQtyInput],
    replace_missing: bool = False,
) -> SxQcInspection:
    inspection = SxQcInspection.objects.select_for_update().get(pk=inspection_id)
    failed_slugs = set(
        inspection.criteria_lines.filter(is_pass=False)
        .exclude(team_slug="")
        .values_list("team_slug", flat=True)
    )
    keep = {item.slug for item in team_qty if item.slug}
    for item in team_qty:
        slug = (item.slug or "").strip().lower()
        if not slug:
            continue
        status = _team_result_status(
            qty_pass=item.qty_pass or Decimal("0"),
            qty_fail=item.qty_fail or Decimal("0"),
            failed_criteria=slug in failed_slugs,
        )
        SxQcInspectionTeamResult.objects.update_or_create(
            inspection=inspection,
            team_slug=slug,
            defaults={
                "qty_pass": item.qty_pass or Decimal("0"),
                "qty_fail": item.qty_fail or Decimal("0"),
                "result": status,
            },
        )
    if replace_missing and keep:
        inspection.team_results.exclude(team_slug__in=keep).delete()
    return inspection


def pending_inspection_team_labels(inspection: SxQcInspection, teams: list[QcTeam]) -> list[str]:
    """Tổ chưa lưu (còn pending) — bắt buộc lưu hết trước khi chốt."""
    if not teams:
        return []
    saved = {
        slug
        for slug, result in inspection.team_results.values_list("team_slug", "result")
        if result and result != SxQcInspectionTeamResult.RESULT_PENDING
    }
    return [t.label for t in teams if t.slug not in saved]


@transaction.atomic
def reopen_inspection(*, inspection_id: int) -> SxQcInspection:
    inspection = SxQcInspection.objects.select_for_update().get(pk=inspection_id)
    if inspection.status != "done":
        raise QcError("Phiếu kiểm tra chưa chốt.")
    inspection.status = "draft"
    inspection.result = SxQcInspection.RESULT_PENDING
    inspection.save(update_fields=["status", "result"])
    qc_req_id = inspection.qc_request_id
    if qc_req_id:
        qc_req = SxQcRequest.objects.select_for_update().get(pk=qc_req_id)
        if qc_req.status == "done":
            qc_req.status = "in_progress"
            qc_req.save(update_fields=["status"])
        mo = qc_req.production_order
        if mo is not None:
            from san_xuat.services.dispatch import _recompute_mo_progress

            _recompute_mo_progress(mo)
    return inspection


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

    method = getattr(standard, "sampling_method", None)
    sample = compute_sample_qty(method, qc_req.qty or Decimal("0"))
    if (getattr(method, "method_type", "") or "") == SxQcSamplingMethod.TYPE_AQL:
        aql_note = (
            f"AQL {method.aql_level}% · mức {method.inspection_level} · "
            f"lô {qc_req.qty} → mẫu {sample.required_qty}, "
            f"chấp nhận ≤ {sample.max_defect_allowed} lỗi"
        )
        notes = f"{notes}\n{aql_note}".strip() if notes else aql_note
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
    team_qty: list[TeamQtyInput] | None = None,
) -> SxQcInspection:
    inspection = save_inspection_detail_lines(
        inspection_id=inspection_id,
        criteria_lines=criteria_lines,
        defect_lines=defect_lines,
    )
    if team_qty is not None:
        save_inspection_team_results(inspection_id=inspection.pk, team_qty=team_qty)
    inspection = SxQcInspection.objects.select_for_update().get(pk=inspection.pk)
    if inspection.status == "done":
        raise QcError("Phiếu kiểm tra đã chốt.")

    sample_qty = inspection.qty_sample or Decimal("0")
    defect_total = sum(
        (line.qty or Decimal("0") for line in inspection.defect_lines.all()),
        Decimal("0"),
    )
    stored_qty = list(inspection.team_results.all())
    mo = getattr(getattr(inspection, "qc_request", None), "production_order", None)
    teams = ob_qc_teams(mo=mo) if mo else []
    pending = pending_inspection_team_labels(inspection, teams)
    if pending:
        raise QcError(
            "Chưa lưu đủ tổ (" + ", ".join(pending) + ") — lưu từng tổ trước khi chốt phiếu."
        )
    if stored_qty:
        fail_qty = sum((row.qty_fail or Decimal("0") for row in stored_qty), Decimal("0"))
        pass_qty = sum((row.qty_pass or Decimal("0") for row in stored_qty), Decimal("0"))
    elif defect_lines is not None and defect_total > 0:
        fail_qty = defect_total
        pass_qty = qty_pass if qty_pass is not None else (
            sample_qty - fail_qty if sample_qty > 0 else Decimal("0")
        )
    else:
        fail_qty = qty_fail or Decimal("0")
        if qty_pass is not None:
            pass_qty = qty_pass
        elif sample_qty > 0:
            pass_qty = sample_qty - fail_qty
        else:
            pass_qty = Decimal("0")

    if fail_qty < 0:
        raise QcError("SL lỗi không được âm.")
    if pass_qty < 0:
        raise QcError("SL đạt không được âm.")
    if not stored_qty:
        if sample_qty > 0 and fail_qty > sample_qty:
            raise QcError("Tổng SL lỗi vượt quá SL mẫu.")
        if sample_qty > 0 and (pass_qty + fail_qty) > sample_qty:
            raise QcError("Tổng SL đạt + lỗi vượt quá SL mẫu.")

    failed_criteria = inspection.criteria_lines.filter(is_pass=False).exists()

    # Số lỗi được phép: AQL cho phép tới Ac lỗi trên mẫu; các cách lấy mẫu khác = 0.
    allowed_defects = Decimal("0")
    method = getattr(inspection.standard_set, "sampling_method", None)
    if method and (method.method_type or "") == SxQcSamplingMethod.TYPE_AQL:
        lot_qty = getattr(inspection.qc_request, "qty", None) or sample_qty
        allowed_defects = compute_sample_qty(method, lot_qty).max_defect_allowed

    inspection.qty_pass = pass_qty
    inspection.qty_fail = fail_qty
    inspection.notes = notes or inspection.notes
    inspection.result = (
        SxQcInspection.RESULT_FAIL
        if fail_qty > allowed_defects or failed_criteria
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

    mo = getattr(getattr(inspection, "qc_request", None), "production_order", None)
    if mo is not None:
        from san_xuat.services.dispatch import _recompute_mo_progress

        _recompute_mo_progress(mo)
    return inspection
