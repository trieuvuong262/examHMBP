"""Kế hoạch SX: KHTT, import KV, explode KH NVL."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from kho_npl.models import Material
from kho_npl.services.reservation import material_available_qty
from kho_npl.services.stock import material_total_qty
from kiotviet.models import KvOrder, KvOrderLine
from kiotviet.sync_service import current_retailer

from san_xuat.hub_models import (
    SxDetailPlan,
    SxDetailPlanLine,
    SxMaterialPlan,
    SxMaterialPlanLine,
    SxNplPurchaseRequest,
    SxNplPurchaseRequestLine,
    SxOverallPlan,
    SxOverallPlanLine,
    SxPurchaseOrder,
    SxPurchaseOrderLine,
)
from san_xuat.models import ProductTechDoc
from san_xuat.services.bom import get_active_bom


class PlanningError(Exception):
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


def _resolve_product_name(product_code: str, fallback: str = "") -> str:
    code = (product_code or "").strip()
    if not code:
        return fallback
    doc = ProductTechDoc.objects.filter(product_code__iexact=code, is_active=True).first()
    if doc and doc.product_name:
        return doc.product_name
    return fallback or code


@transaction.atomic
def create_overall_plan(
    *,
    name: str,
    date_from,
    date_to,
    code: str | None = None,
    source: str = SxOverallPlan.SOURCE_FORECAST,
    notes: str = "",
    user=None,
) -> SxOverallPlan:
    if date_from and date_to and date_from > date_to:
        raise PlanningError("Ngày bắt đầu không được sau ngày kết thúc.")
    return SxOverallPlan.objects.create(
        code=(code or "").strip() or _next_code("KHTT", SxOverallPlan),
        name=(name or "").strip() or "Kế hoạch tổng thể",
        date_from=date_from or timezone.localdate(),
        date_to=date_to or timezone.localdate(),
        source=source or SxOverallPlan.SOURCE_FORECAST,
        status=SxOverallPlan.STATUS_DRAFT,
        notes=notes or "",
        is_demo=False,
        created_by=user,
    )


@transaction.atomic
def add_overall_plan_line(
    *,
    plan_id: int,
    product_code: str,
    qty_planned: Decimal,
    qty_required: Decimal | None = None,
    product_name: str = "",
    capacity_per_day: Decimal = Decimal("0"),
) -> SxOverallPlanLine:
    plan = SxOverallPlan.objects.select_for_update().get(pk=plan_id)
    if plan.status != SxOverallPlan.STATUS_DRAFT:
        raise PlanningError("Chỉ thêm dòng khi KHTT đang nháp.")
    code = (product_code or "").strip()
    if not code:
        raise PlanningError("Thiếu mã sản phẩm.")
    qty = qty_planned or Decimal("0")
    if qty <= 0:
        raise PlanningError("SL kế hoạch phải > 0.")
    return SxOverallPlanLine.objects.create(
        plan=plan,
        product_code=code,
        product_name=(product_name or "").strip() or _resolve_product_name(code),
        qty_required=qty_required if qty_required is not None else qty,
        qty_planned=qty,
        capacity_per_day=capacity_per_day or Decimal("0"),
    )


@transaction.atomic
def confirm_overall_plan(*, plan_id: int) -> SxOverallPlan:
    plan = SxOverallPlan.objects.select_for_update().prefetch_related("lines").get(pk=plan_id)
    if plan.status != SxOverallPlan.STATUS_DRAFT:
        raise PlanningError("KHTT đã xác nhận hoặc không ở trạng thái nháp.")
    if not plan.lines.exists():
        raise PlanningError("KHTT phải có ít nhất một dòng sản phẩm.")
    plan.status = SxOverallPlan.STATUS_CONFIRMED
    plan.save(update_fields=["status"])
    return plan


@transaction.atomic
def build_overall_lines_from_kv_order(
    *,
    plan_id: int,
    kv_order_kiotviet_id: int | None = None,
    kv_order_code: str = "",
) -> list[SxOverallPlanLine]:
    plan = SxOverallPlan.objects.select_for_update().get(pk=plan_id)
    if plan.status != SxOverallPlan.STATUS_DRAFT:
        raise PlanningError("Chỉ import đơn KV khi KHTT đang nháp.")

    retailer = current_retailer()
    order = None
    if kv_order_kiotviet_id:
        order = KvOrder.objects.filter(
            retailer=retailer,
            kiotviet_id=kv_order_kiotviet_id,
            is_deleted=False,
        ).first()
    if not order and (kv_order_code or "").strip():
        order = KvOrder.objects.filter(
            retailer=retailer,
            code__iexact=kv_order_code.strip(),
            is_deleted=False,
        ).order_by("-purchase_date", "-id").first()
    if not order:
        raise PlanningError("Không tìm thấy đơn KV trong dữ liệu đã sync.")

    lines = KvOrderLine.objects.filter(
        retailer=retailer,
        order_kiotviet_id=order.kiotviet_id,
    ).order_by("line_index", "id")
    if not lines.exists():
        raise PlanningError("Đơn KV không có dòng hàng.")

    created: list[SxOverallPlanLine] = []
    for kv_line in lines:
        code = (kv_line.product_code or "").strip()
        qty = Decimal(str(kv_line.quantity or 0))
        if not code or qty <= 0:
            continue
        created.append(
            SxOverallPlanLine.objects.create(
                plan=plan,
                product_code=code,
                product_name=(kv_line.product_name or "").strip() or _resolve_product_name(code),
                qty_required=qty,
                qty_planned=qty,
                kv_order_kiotviet_id=order.kiotviet_id,
                kv_order_code=order.code or "",
            )
        )
    if not created:
        raise PlanningError("Không có dòng hàng hợp lệ để import.")

    plan.source = SxOverallPlan.SOURCE_SALES_ORDER
    plan.save(update_fields=["source"])
    return created


@transaction.atomic
def explode_material_plan(
    *,
    overall_plan_id: int,
    code: str | None = None,
    name: str = "",
) -> SxMaterialPlan:
    overall = (
        SxOverallPlan.objects.select_for_update()
        .prefetch_related("lines")
        .get(pk=overall_plan_id)
    )
    if overall.status != SxOverallPlan.STATUS_CONFIRMED:
        raise PlanningError("KHTT phải đã xác nhận trước khi tính KH NVL.")
    if not overall.lines.exists():
        raise PlanningError("KHTT không có dòng sản phẩm.")

    material_req: dict[str, Decimal] = {}
    material_names: dict[str, str] = {}
    skipped_products: list[str] = []

    for line in overall.lines.all():
        qty_planned = line.qty_planned or line.qty_required or Decimal("0")
        if qty_planned <= 0:
            continue
        product_code = (line.product_code or "").strip()
        doc = ProductTechDoc.objects.filter(product_code__iexact=product_code, is_active=True).first()
        if not doc:
            skipped_products.append(product_code)
            continue
        bom = get_active_bom(doc)
        if not bom:
            skipped_products.append(product_code)
            continue
        for bl in bom.lines.select_related("material").all():
            mat_code = bl.material.code
            need = bl.qty_with_scrap * qty_planned
            material_req[mat_code] = material_req.get(mat_code, Decimal("0")) + need
            material_names[mat_code] = bl.material.name

    if not material_req:
        raise PlanningError("Không explode được NVL — cần BOM active cho ít nhất một mã SP.")

    mat_plan = (
        SxMaterialPlan.objects.filter(
            overall_plan=overall,
            is_demo=False,
            status=SxOverallPlan.STATUS_DRAFT,
        )
        .order_by("-id")
        .first()
    )
    if not mat_plan:
        mat_plan = SxMaterialPlan.objects.create(
            code=(code or "").strip() or _next_code("KHNVL", SxMaterialPlan),
            name=(name or "").strip() or f"KHNVL từ {overall.code}",
            overall_plan=overall,
            status=SxOverallPlan.STATUS_DRAFT,
            is_demo=False,
        )
    else:
        mat_plan.lines.all().delete()

    note_parts = []
    if skipped_products:
        note_parts.append(f"SP không có BOM active: {', '.join(sorted(set(skipped_products)))}")
    if note_parts:
        mat_plan.notes = " · ".join(note_parts)
        mat_plan.save(update_fields=["notes"])

    create_lines: list[SxMaterialPlanLine] = []
    for mat_code, qty_req in sorted(material_req.items()):
        mat = Material.objects.filter(code__iexact=mat_code, is_active=True).first()
        on_hand = material_total_qty(mat) if mat else Decimal("0")
        available = material_available_qty(mat) if mat else Decimal("0")
        inbound = _expected_inbound_qty(mat_code)
        # Shortfall theo available (đã trừ giữ chỗ), vẫn lưu on_hand để đối chiếu
        shortfall = max(Decimal("0"), qty_req - available - inbound)
        create_lines.append(
            SxMaterialPlanLine(
                plan=mat_plan,
                material_code=mat_code,
                material_name=material_names.get(mat_code, mat.name if mat else ""),
                qty_required=qty_req.quantize(Decimal("0.0001")),
                qty_on_hand=on_hand.quantize(Decimal("0.0001")),
                qty_expected_inbound=inbound.quantize(Decimal("0.0001")),
                qty_shortfall=shortfall.quantize(Decimal("0.0001")),
            )
        )
    SxMaterialPlanLine.objects.bulk_create(create_lines)
    return mat_plan


def _expected_inbound_qty(material_code: str) -> Decimal:
    """SL còn lại trên DMH/PO mở (confirmed/draft) chưa nhận đủ."""
    open_statuses = ("draft", "confirmed", "ordered", "partial")
    total = Decimal("0")
    lines = (
        SxPurchaseOrderLine.objects.filter(
            material_code__iexact=material_code,
            order__is_demo=False,
            order__status__in=open_statuses,
        )
        .select_related("order")
    )
    for line in lines:
        ordered = line.qty_ordered or Decimal("0")
        received = line.qty_received or Decimal("0")
        remaining = ordered - received
        if remaining > 0:
            total += remaining
    return total.quantize(Decimal("0.0001"))


@transaction.atomic
def confirm_material_plan(*, plan_id: int) -> SxMaterialPlan:
    plan = SxMaterialPlan.objects.select_for_update().prefetch_related("lines").get(pk=plan_id)
    if plan.status != SxOverallPlan.STATUS_DRAFT:
        raise PlanningError("KHNVL đã xác nhận hoặc không ở trạng thái nháp.")
    if not plan.lines.exists():
        raise PlanningError("KHNVL phải có ít nhất một dòng NVL.")
    plan.status = SxOverallPlan.STATUS_CONFIRMED
    plan.save(update_fields=["status"])
    from kho_npl.services.reservation import upsert_reservations_for_khnvl

    upsert_reservations_for_khnvl(plan=plan)
    return plan


@transaction.atomic
def build_pr_from_material_plan(
    *,
    material_plan_id: int,
    only_shortfall: bool = True,
    code: str | None = None,
    due_date=None,
    notes: str = "",
) -> SxNplPurchaseRequest:
    mat_plan = (
        SxMaterialPlan.objects.select_for_update()
        .prefetch_related("lines")
        .get(pk=material_plan_id)
    )
    if mat_plan.status != SxOverallPlan.STATUS_CONFIRMED:
        raise PlanningError("KHNVL phải đã xác nhận trước khi sinh YCM.")

    lines_qs = mat_plan.lines.all()
    if only_shortfall:
        lines_qs = lines_qs.filter(qty_shortfall__gt=0)
    if not lines_qs.exists():
        raise PlanningError("Không có dòng shortfall để tạo YCM.")

    pr = (
        SxNplPurchaseRequest.objects.filter(
            material_plan=mat_plan,
            is_demo=False,
            status=SxNplPurchaseRequest.STATUS_DRAFT,
        )
        .order_by("-id")
        .first()
    )
    if pr:
        pr.lines.all().delete()
        pr.due_date = due_date or pr.due_date
        pr.notes = notes or pr.notes
        pr.save(update_fields=["due_date", "notes"])
    else:
        pr = SxNplPurchaseRequest.objects.create(
            code=(code or "").strip() or _next_code("YCM", SxNplPurchaseRequest),
            material_plan=mat_plan,
            request_date=timezone.localdate(),
            due_date=due_date,
            status=SxNplPurchaseRequest.STATUS_DRAFT,
            notes=notes or "",
            is_demo=False,
        )

    create_lines = [
        SxNplPurchaseRequestLine(
            request=pr,
            material_code=line.material_code,
            material_name=line.material_name,
            qty=(line.qty_shortfall if only_shortfall else line.qty_required).quantize(Decimal("0.0001")),
        )
        for line in lines_qs
        if (line.qty_shortfall if only_shortfall else line.qty_required) > 0
    ]
    SxNplPurchaseRequestLine.objects.bulk_create(create_lines)
    return pr


@transaction.atomic
def submit_npl_purchase_request(*, request_id: int) -> SxNplPurchaseRequest:
    pr = SxNplPurchaseRequest.objects.select_for_update().prefetch_related("lines").get(pk=request_id)
    if pr.status != SxNplPurchaseRequest.STATUS_DRAFT:
        raise PlanningError("Chỉ gửi YCM ở trạng thái nháp.")
    if not pr.lines.exists():
        raise PlanningError("YCM phải có ít nhất một dòng NVL.")
    pr.status = SxNplPurchaseRequest.STATUS_SUBMITTED
    pr.save(update_fields=["status"])
    return pr


@transaction.atomic
def approve_npl_purchase_request(*, request_id: int) -> SxNplPurchaseRequest:
    pr = SxNplPurchaseRequest.objects.select_for_update().get(pk=request_id)
    if pr.status != SxNplPurchaseRequest.STATUS_SUBMITTED:
        raise PlanningError("Chỉ duyệt YCM đã gửi.")
    pr.status = SxNplPurchaseRequest.STATUS_APPROVED
    pr.save(update_fields=["status"])
    return pr


@transaction.atomic
def reject_npl_purchase_request(*, request_id: int, notes: str = "") -> SxNplPurchaseRequest:
    pr = SxNplPurchaseRequest.objects.select_for_update().get(pk=request_id)
    if pr.status != SxNplPurchaseRequest.STATUS_SUBMITTED:
        raise PlanningError("Chỉ từ chối YCM đã gửi.")
    pr.status = SxNplPurchaseRequest.STATUS_REJECTED
    if notes:
        pr.notes = notes
        pr.save(update_fields=["status", "notes"])
    else:
        pr.save(update_fields=["status"])
    return pr


@transaction.atomic
def explode_detail_plan_from_overall(
    *,
    overall_plan_id: int,
    code: str | None = None,
    name: str = "",
) -> SxDetailPlan:
    from datetime import timedelta

    overall = (
        SxOverallPlan.objects.select_for_update()
        .prefetch_related("lines")
        .get(pk=overall_plan_id)
    )
    if overall.status != SxOverallPlan.STATUS_CONFIRMED:
        raise PlanningError("KHTT phải đã xác nhận trước khi lập KHCT.")
    if not overall.lines.exists():
        raise PlanningError("KHTT không có dòng sản phẩm.")
    if overall.date_from > overall.date_to:
        raise PlanningError("KHTT có kỳ ngày không hợp lệ.")

    num_days = (overall.date_to - overall.date_from).days + 1
    if num_days <= 0:
        raise PlanningError("KHTT không có ngày trong kỳ.")

    detail = (
        SxDetailPlan.objects.filter(
            overall_plan=overall,
            is_demo=False,
            status=SxOverallPlan.STATUS_DRAFT,
        )
        .order_by("-id")
        .first()
    )
    if detail:
        detail.lines.all().delete()
        detail.date_from = overall.date_from
        detail.date_to = overall.date_to
        detail.name = (name or "").strip() or detail.name
        detail.save(update_fields=["date_from", "date_to", "name"])
    else:
        detail = SxDetailPlan.objects.create(
            code=(code or "").strip() or _next_code("KHCT", SxDetailPlan),
            name=(name or "").strip() or f"KHCT từ {overall.code}",
            overall_plan=overall,
            date_from=overall.date_from,
            date_to=overall.date_to,
            status=SxOverallPlan.STATUS_DRAFT,
            is_demo=False,
        )

    create_lines: list[SxDetailPlanLine] = []
    for line in overall.lines.all():
        qty_planned = line.qty_planned or line.qty_required or Decimal("0")
        if qty_planned <= 0:
            continue
        daily_qty = (qty_planned / Decimal(num_days)).quantize(Decimal("0.01"))
        remainder = qty_planned - (daily_qty * num_days)
        for day_offset in range(num_days):
            plan_date = overall.date_from + timedelta(days=day_offset)
            qty = daily_qty
            if day_offset == num_days - 1:
                qty = (qty + remainder).quantize(Decimal("0.01"))
            if qty <= 0:
                continue
            create_lines.append(
                SxDetailPlanLine(
                    plan=detail,
                    plan_date=plan_date,
                    product_code=line.product_code,
                    product_name=line.product_name,
                    qty=qty,
                )
            )
    if not create_lines:
        raise PlanningError("Không tạo được dòng KHCT — kiểm tra SL kế hoạch trên KHTT.")
    SxDetailPlanLine.objects.bulk_create(create_lines)
    return detail


def _expected_inbound_qty(material_code: str) -> Decimal:
    """SL còn lại trên DMH/PO mở (draft/confirmed) chưa nhận đủ."""
    total = Decimal("0")
    lines = SxPurchaseOrderLine.objects.filter(
        material_code__iexact=material_code,
        order__is_demo=False,
        order__status__in=(
            SxPurchaseOrder.STATUS_DRAFT,
            SxPurchaseOrder.STATUS_CONFIRMED,
        ),
    )
    for line in lines:
        ordered = line.qty_ordered or Decimal("0")
        received = line.qty_received or Decimal("0")
        remaining = ordered - received
        if remaining > 0:
            total += remaining
    return total.quantize(Decimal("0.0001"))


@dataclass
class CapacityDayWarning:
    plan_date: object
    qty_planned: Decimal
    capacity_total: Decimal
    over_by: Decimal
    team_label: str = ""


def check_detail_plan_capacity(*, plan_id: int) -> list[CapacityDayWarning]:
    """So sánh tổng SL KHCT theo ngày với tổng NL tổ/ngày (finite capacity)."""
    from san_xuat.hub_models import SxWorkCenter

    plan = SxDetailPlan.objects.prefetch_related("lines").get(pk=plan_id)
    centers = list(
        SxWorkCenter.objects.filter(is_active=True, is_demo=False).order_by("code")
    )
    total_cap = sum((c.capacity_per_day or Decimal("0") for c in centers), Decimal("0"))
    if total_cap <= 0:
        # Fallback: sum capacity_per_day trên dòng KHTT nếu có
        if plan.overall_plan_id:
            from san_xuat.hub_models import SxOverallPlanLine

            total_cap = sum(
                (
                    ln.capacity_per_day or Decimal("0")
                    for ln in SxOverallPlanLine.objects.filter(plan_id=plan.overall_plan_id)
                ),
                Decimal("0"),
            )

    by_day: dict = {}
    for line in plan.lines.all():
        key = line.plan_date
        by_day[key] = by_day.get(key, Decimal("0")) + (line.qty or Decimal("0"))

    warnings: list[CapacityDayWarning] = []
    for day, qty in sorted(by_day.items()):
        if total_cap > 0 and qty > total_cap:
            warnings.append(
                CapacityDayWarning(
                    plan_date=day,
                    qty_planned=qty.quantize(Decimal("0.01")),
                    capacity_total=total_cap.quantize(Decimal("0.01")),
                    over_by=(qty - total_cap).quantize(Decimal("0.01")),
                )
            )
    return warnings


def assign_detail_plan_work_centers(*, plan_id: int) -> int:
    """Gán tổ NL round-robin vào dòng KHCT chưa có team (MVP)."""
    from san_xuat.hub_models import SxWorkCenter

    plan = SxDetailPlan.objects.prefetch_related("lines").get(pk=plan_id)
    centers = list(
        SxWorkCenter.objects.filter(is_active=True, is_demo=False).order_by("code")
    )
    if not centers:
        return 0
    updated = 0
    for idx, line in enumerate(plan.lines.filter(team_label="").order_by("plan_date", "id")):
        wc = centers[idx % len(centers)]
        line.work_center = wc
        line.team_label = wc.team_label or wc.name
        line.save(update_fields=["work_center", "team_label"])
        updated += 1
    return updated


@transaction.atomic
def confirm_detail_plan(*, plan_id: int, allow_over_capacity: bool = True) -> SxDetailPlan:
    plan = SxDetailPlan.objects.select_for_update().prefetch_related("lines").get(pk=plan_id)
    if plan.status != SxOverallPlan.STATUS_DRAFT:
        raise PlanningError("KHCT đã xác nhận hoặc không ở trạng thái nháp.")
    if not plan.lines.exists():
        raise PlanningError("KHCT phải có ít nhất một dòng theo ngày.")
    over = check_detail_plan_capacity(plan_id=plan.pk)
    if over and not allow_over_capacity:
        first = over[0]
        raise PlanningError(
            f"KHCT vượt năng lực ngày {first.plan_date}: "
            f"kế hoạch {first.qty_planned} > NL {first.capacity_total} "
            f"(dư {first.over_by})."
        )
    if over:
        note = (
            f"Cảnh báo NL: {len(over)} ngày vượt capacity "
            f"(vd {over[0].plan_date}: +{over[0].over_by})."
        )
        plan.notes = f"{plan.notes}\n{note}".strip() if plan.notes else note
    plan.status = SxOverallPlan.STATUS_CONFIRMED
    plan.save(update_fields=["status", "notes"] if over else ["status"])
    return plan


@transaction.atomic
def build_po_from_purchase_request(
    *,
    purchase_request_id: int,
    supplier_name: str = "",
    code: str | None = None,
    notes: str = "",
) -> SxPurchaseOrder:
    pr = (
        SxNplPurchaseRequest.objects.select_for_update()
        .prefetch_related("lines")
        .get(pk=purchase_request_id)
    )
    if pr.status != SxNplPurchaseRequest.STATUS_APPROVED:
        raise PlanningError("Chỉ tạo DMH từ YCM đã duyệt.")
    if not pr.lines.exists():
        raise PlanningError("YCM không có dòng NVL.")

    po = (
        SxPurchaseOrder.objects.filter(
            purchase_request=pr,
            is_demo=False,
            status=SxPurchaseOrder.STATUS_DRAFT,
        )
        .order_by("-id")
        .first()
    )
    if po:
        po.lines.all().delete()
        po.supplier_name = (supplier_name or "").strip() or po.supplier_name
        po.notes = notes or po.notes
        po.save(update_fields=["supplier_name", "notes"])
    else:
        po = SxPurchaseOrder.objects.create(
            code=(code or "").strip() or _next_code("DMH", SxPurchaseOrder),
            supplier_name=(supplier_name or "").strip(),
            purchase_request=pr,
            status=SxPurchaseOrder.STATUS_DRAFT,
            notes=notes or "",
            is_demo=False,
        )

    create_lines = [
        SxPurchaseOrderLine(
            order=po,
            material_code=line.material_code,
            material_name=line.material_name,
            qty_ordered=line.qty.quantize(Decimal("0.0001")),
            qty_received=Decimal("0"),
        )
        for line in pr.lines.all()
        if line.qty > 0
    ]
    if not create_lines:
        raise PlanningError("YCM không có SL mua > 0.")
    SxPurchaseOrderLine.objects.bulk_create(create_lines)
    return po


@transaction.atomic
def confirm_purchase_order(*, order_id: int) -> SxPurchaseOrder:
    po = SxPurchaseOrder.objects.select_for_update().prefetch_related("lines").get(pk=order_id)
    if po.status != SxPurchaseOrder.STATUS_DRAFT:
        raise PlanningError("Chỉ xác nhận DMH ở trạng thái nháp.")
    if not po.lines.exists():
        raise PlanningError("DMH phải có ít nhất một dòng NVL.")
    po.status = SxPurchaseOrder.STATUS_CONFIRMED
    po.save(update_fields=["status"])
    return po


@transaction.atomic
def link_kv_purchase_to_po(
    *,
    order_id: int,
    kv_purchase_kiotviet_id: int | None = None,
    kv_purchase_code: str = "",
) -> SxPurchaseOrder:
    from kiotviet.models import KvPurchaseOrder, KvPurchaseOrderLine
    from kiotviet.sync_service import current_retailer

    po = SxPurchaseOrder.objects.select_for_update().prefetch_related("lines").get(pk=order_id)
    if po.status == SxPurchaseOrder.STATUS_RECEIVED and po.kv_purchase_kiotviet_id:
        raise PlanningError("DMH đã liên kết phiếu nhập KV.")

    purchase = None
    retailer = current_retailer()
    if kv_purchase_kiotviet_id:
        purchase = KvPurchaseOrder.objects.filter(
            retailer=retailer,
            kiotviet_id=kv_purchase_kiotviet_id,
        ).first()
    if not purchase and (kv_purchase_code or "").strip():
        purchase = (
            KvPurchaseOrder.objects.filter(retailer=retailer, code__iexact=kv_purchase_code.strip())
            .order_by("-purchase_date", "-id")
            .first()
        )
    if not purchase:
        raise PlanningError("Không tìm thấy phiếu nhập KV trong dữ liệu đã sync.")

    kv_lines = KvPurchaseOrderLine.objects.filter(
        retailer=retailer,
        purchase_order_kiotviet_id=purchase.kiotviet_id,
    )
    qty_by_code: dict[str, Decimal] = {}
    for kv_line in kv_lines:
        code_key = (kv_line.product_code or "").strip().upper()
        if not code_key:
            continue
        qty = Decimal(str(kv_line.quantity or 0)).quantize(Decimal("0.0001"))
        qty_by_code[code_key] = qty_by_code.get(code_key, Decimal("0")) + qty

    for line in po.lines.all():
        key = (line.material_code or "").strip().upper()
        if key in qty_by_code:
            line.qty_received = qty_by_code[key]
            line.save(update_fields=["qty_received"])

    if not (po.supplier_name or "").strip() and purchase.supplier_name:
        po.supplier_name = purchase.supplier_name

    po.kv_purchase_kiotviet_id = purchase.kiotviet_id
    po.kv_purchase_code = purchase.code or ""
    po.status = SxPurchaseOrder.STATUS_RECEIVED
    po.save(update_fields=["kv_purchase_kiotviet_id", "kv_purchase_code", "status", "supplier_name"])
    return po
