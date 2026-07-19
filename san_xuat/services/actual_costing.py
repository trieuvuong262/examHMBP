"""Giá thành thực tế — NVL xuất + lương SP + phí GC."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from kho_npl.models import StockIssue, StockIssueLine
from san_xuat.hub_models import SxActualCostSheet, SxProductionOrder, SxSubcontractOrder
from san_xuat.services.phase3 import compute_piece_rate_pay


class ActualCostError(Exception):
    pass


@dataclass
class ActualCostBreakdown:
    material_cost: Decimal
    labor_cost: Decimal
    subcontract_cost: Decimal
    total_cost: Decimal
    qty_basis: Decimal
    unit_cost: Decimal
    material_lines: list[dict]
    labor_rows: list


def compute_actual_cost_for_mo(*, production_order_id: int) -> ActualCostBreakdown:
    mo = SxProductionOrder.objects.get(pk=production_order_id)

    # NVL: dòng phiếu xuất đã post gắn LSX
    issue_ids = list(
        StockIssue.objects.filter(
            production_order=mo.code,
            status="posted",
        ).values_list("pk", flat=True)
    )
    material_lines: list[dict] = []
    material_cost = Decimal("0")
    if issue_ids:
        for line in (
            StockIssueLine.objects.filter(issue_id__in=issue_ids)
            .select_related("material", "issue")
            .order_by("pk")
        ):
            qty = line.quantity or Decimal("0")
            price = line.unit_price or Decimal("0")
            amount = (qty * price).quantize(Decimal("0.01"))
            material_cost += amount
            material_lines.append(
                {
                    "issue": line.issue.number,
                    "material": line.material.code if line.material_id else "",
                    "qty": qty,
                    "unit_price": price,
                    "amount": amount,
                }
            )

    labor_rows = compute_piece_rate_pay(production_order_id=mo.pk)
    labor_cost = sum((r.amount for r in labor_rows), Decimal("0"))

    subcontract_cost = (
        SxSubcontractOrder.objects.filter(
            production_order=mo,
            is_demo=False,
            status__in=(
                SxSubcontractOrder.STATUS_SENT,
                SxSubcontractOrder.STATUS_RECEIVED,
                SxSubcontractOrder.STATUS_DONE,
            ),
        ).aggregate(t=Sum("service_fee"))["t"]
        or Decimal("0")
    )

    total = (material_cost + labor_cost + subcontract_cost).quantize(Decimal("0.01"))
    qty_basis = mo.qty_done or Decimal("0")
    if qty_basis <= 0:
        qty_basis = mo.qty or Decimal("0")
    unit = (total / qty_basis).quantize(Decimal("0.01")) if qty_basis > 0 else Decimal("0")

    return ActualCostBreakdown(
        material_cost=material_cost.quantize(Decimal("0.01")),
        labor_cost=labor_cost.quantize(Decimal("0.01")),
        subcontract_cost=subcontract_cost.quantize(Decimal("0.01")),
        total_cost=total,
        qty_basis=qty_basis,
        unit_cost=unit,
        material_lines=material_lines,
        labor_rows=labor_rows,
    )


def _next_actual_code() -> str:
    year = timezone.localdate().year
    prefix = f"GTT-{year}-"
    last = (
        SxActualCostSheet.objects.filter(code__startswith=prefix)
        .order_by("-code")
        .values_list("code", flat=True)
        .first()
    )
    n = 1
    if last:
        try:
            n = int(last.split("-")[-1]) + 1
        except ValueError:
            n = 1
    return f"{prefix}{n:04d}"


@transaction.atomic
def create_or_refresh_actual_cost(*, production_order_id: int, close: bool = False) -> SxActualCostSheet:
    mo = SxProductionOrder.objects.select_for_update().get(pk=production_order_id)
    br = compute_actual_cost_for_mo(production_order_id=mo.pk)

    sheet = (
        SxActualCostSheet.objects.filter(
            production_order=mo,
            status=SxActualCostSheet.STATUS_DRAFT,
            is_demo=False,
        )
        .order_by("-pk")
        .first()
    )
    if not sheet:
        sheet = SxActualCostSheet(
            code=_next_actual_code(),
            production_order=mo,
            is_demo=False,
        )

    sheet.material_cost = br.material_cost
    sheet.labor_cost = br.labor_cost
    sheet.subcontract_cost = br.subcontract_cost
    sheet.total_cost = br.total_cost
    sheet.qty_basis = br.qty_basis
    sheet.unit_cost = br.unit_cost
    if close:
        if sheet.status == SxActualCostSheet.STATUS_CLOSED:
            raise ActualCostError("Bảng GT thực đã chốt.")
        sheet.status = SxActualCostSheet.STATUS_CLOSED
        sheet.closed_at = timezone.now()
    sheet.save()
    return sheet
