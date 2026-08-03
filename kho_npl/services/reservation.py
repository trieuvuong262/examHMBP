"""Giữ chỗ tồn NPL — trừ khỏi available cho KHNVL / YCX."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from kho_npl.models import Material, StockReservation
from kho_npl.services.stock import material_total_qty


class ReservationError(Exception):
    pass


def material_reserved_qty(material: Material) -> Decimal:
    total = (
        StockReservation.objects.filter(
            material=material,
            status=StockReservation.STATUS_ACTIVE,
        ).aggregate(t=Sum("quantity"))["t"]
        or Decimal("0")
    )
    return total


def material_available_qty(material: Material) -> Decimal:
    """Tồn on-hand − đang giữ chỗ (không âm)."""
    on_hand = material_total_qty(material)
    reserved = material_reserved_qty(material)
    avail = on_hand - reserved
    return avail if avail > 0 else Decimal("0")


@transaction.atomic
def upsert_reservations_for_ycx(*, request) -> list[StockReservation]:
    """Tạo/cập nhật giữ chỗ active theo dòng YCX (draft/submitted)."""
    from san_xuat.hub_models import SxMaterialIssueRequest

    if not isinstance(request, SxMaterialIssueRequest):
        request = SxMaterialIssueRequest.objects.prefetch_related("lines").get(pk=request)

    # Hủy reservation cũ của cùng ref
    StockReservation.objects.filter(
        ref_type=StockReservation.REF_YCX,
        ref_code=request.code,
        status=StockReservation.STATUS_ACTIVE,
    ).update(status=StockReservation.STATUS_RELEASED)

    mo_code = request.production_order.code if request.production_order_id else ""
    created: list[StockReservation] = []
    for line in request.lines.all():
        qty = (line.qty_requested or Decimal("0")).quantize(Decimal("0.001"))
        if qty <= 0:
            continue
        mat = Material.objects.filter(code__iexact=line.material_code, is_active=True).first()
        if not mat:
            continue
        created.append(
            StockReservation.objects.create(
                material=mat,
                quantity=qty,
                ref_type=StockReservation.REF_YCX,
                ref_code=request.code,
                production_order_code=mo_code,
                status=StockReservation.STATUS_ACTIVE,
                notes=f"YCX {request.code}",
            )
        )
    return created


@transaction.atomic
def consume_reservations_for_ycx(*, ycx_code: str) -> int:
    updated = StockReservation.objects.filter(
        ref_type=StockReservation.REF_YCX,
        ref_code=ycx_code,
        status=StockReservation.STATUS_ACTIVE,
    ).update(status=StockReservation.STATUS_CONSUMED)
    return updated


@transaction.atomic
def release_reservations_for_ycx(*, ycx_code: str) -> int:
    return StockReservation.objects.filter(
        ref_type=StockReservation.REF_YCX,
        ref_code=ycx_code,
        status=StockReservation.STATUS_ACTIVE,
    ).update(status=StockReservation.STATUS_RELEASED)


@transaction.atomic
def upsert_reservations_for_khnvl(*, plan) -> list[StockReservation]:
    """Giữ chỗ tồn NPL cho KHNVL đã xác nhận.

    Giữ tối đa phần tồn khả dụng đang có (không thể giữ hàng chưa về). Số thực
    giữ được ghi lại vào `qty_reserved` của từng dòng KHNVL để biết còn hở bao nhiêu.
    """
    from san_xuat.hub_models import SxMaterialPlan

    if not isinstance(plan, SxMaterialPlan):
        plan = SxMaterialPlan.objects.prefetch_related("lines").get(pk=plan)

    StockReservation.objects.filter(
        ref_type=StockReservation.REF_KHNVL,
        ref_code=plan.code,
        status=StockReservation.STATUS_ACTIVE,
    ).update(status=StockReservation.STATUS_RELEASED)

    created: list[StockReservation] = []
    touched_lines = []
    for line in plan.lines.all():
        qty = (line.qty_required or Decimal("0")).quantize(Decimal("0.001"))
        hold = Decimal("0")
        if qty > 0:
            mat = Material.objects.filter(code__iexact=line.material_code, is_active=True).first()
            if mat:
                # Chỉ giữ phần tồn khả dụng đang thực có
                avail = material_available_qty(mat)
                hold = min(qty, avail)
                if hold > 0:
                    created.append(
                        StockReservation.objects.create(
                            material=mat,
                            quantity=hold,
                            ref_type=StockReservation.REF_KHNVL,
                            ref_code=plan.code,
                            status=StockReservation.STATUS_ACTIVE,
                            notes=f"KHNVL {plan.code}",
                        )
                    )
        if line.qty_reserved != hold:
            line.qty_reserved = hold
            touched_lines.append(line)
    if touched_lines:
        type(touched_lines[0]).objects.bulk_update(touched_lines, ["qty_reserved"])
    return created


def release_reservations_for_khnvl(*, plan) -> int:
    """Giải phóng toàn bộ giữ chỗ của một KHNVL (khi hủy kế hoạch)."""
    from san_xuat.hub_models import SxMaterialPlan

    if not isinstance(plan, SxMaterialPlan):
        plan = SxMaterialPlan.objects.prefetch_related("lines").get(pk=plan)

    freed = StockReservation.objects.filter(
        ref_type=StockReservation.REF_KHNVL,
        ref_code=plan.code,
        status=StockReservation.STATUS_ACTIVE,
    ).update(status=StockReservation.STATUS_RELEASED)

    lines = list(plan.lines.exclude(qty_reserved=Decimal("0")))
    if lines:
        for ln in lines:
            ln.qty_reserved = Decimal("0")
        type(lines[0]).objects.bulk_update(lines, ["qty_reserved"])
    return freed
