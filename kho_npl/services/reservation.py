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
    """Giữ chỗ theo shortfall KHNVL đã xác nhận (qty_required − inbound, capped by available)."""
    from san_xuat.hub_models import SxMaterialPlan

    if not isinstance(plan, SxMaterialPlan):
        plan = SxMaterialPlan.objects.prefetch_related("lines").get(pk=plan)

    StockReservation.objects.filter(
        ref_type=StockReservation.REF_KHNVL,
        ref_code=plan.code,
        status=StockReservation.STATUS_ACTIVE,
    ).update(status=StockReservation.STATUS_RELEASED)

    created: list[StockReservation] = []
    for line in plan.lines.all():
        qty = (line.qty_required or Decimal("0")).quantize(Decimal("0.001"))
        if qty <= 0:
            continue
        mat = Material.objects.filter(code__iexact=line.material_code, is_active=True).first()
        if not mat:
            continue
        # Chỉ giữ phần có thể cover bằng available hiện tại
        avail = material_available_qty(mat)
        hold = min(qty, avail)
        if hold <= 0:
            continue
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
    return created
