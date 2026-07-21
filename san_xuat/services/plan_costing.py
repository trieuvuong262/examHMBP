"""Giá thành kế hoạch: bảng định mức chốt kỳ (C1)."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from san_xuat.hub_models import SxStandardCostLine, SxStandardCostSheet
from san_xuat.models import ProductTechDoc
from san_xuat.services.bom import get_active_bom, get_working_bom
from san_xuat.services.costing import compute_costing
from san_xuat.services.sx_settings import sx_prefix


class PlanCostingError(Exception):
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


@transaction.atomic
def build_standard_sheet_from_bom(
    *,
    name: str,
    date_from,
    date_to,
    code: str | None = None,
    notes: str = "",
    product_codes: list[str] | None = None,
    sheet_id: int | None = None,
) -> SxStandardCostSheet:
    if date_from > date_to:
        raise PlanCostingError("Kỳ giá thành không hợp lệ (từ ngày > đến ngày).")

    if sheet_id:
        sheet = SxStandardCostSheet.objects.select_for_update().get(pk=sheet_id)
        if sheet.status != SxStandardCostSheet.STATUS_DRAFT:
            raise PlanCostingError("Chỉ cập nhật bảng GT ở trạng thái nháp.")
        sheet.lines.all().delete()
        sheet.name = (name or "").strip() or sheet.name
        sheet.date_from = date_from
        sheet.date_to = date_to
        sheet.notes = notes or sheet.notes
        sheet.save(update_fields=["name", "date_from", "date_to", "notes"])
    else:
        sheet = (
            SxStandardCostSheet.objects.filter(
                is_demo=False,
                status=SxStandardCostSheet.STATUS_DRAFT,
                date_from=date_from,
                date_to=date_to,
                name=(name or "").strip(),
            )
            .order_by("-id")
            .first()
        )
        if sheet:
            sheet.lines.all().delete()
            sheet.notes = notes or sheet.notes
            sheet.save(update_fields=["notes"])
        else:
            sheet = SxStandardCostSheet.objects.create(
                code=_code("cost_std", SxStandardCostSheet, code=code),
                name=(name or "").strip() or f"GT định mức {date_from:%d/%m/%Y}–{date_to:%d/%m/%Y}",
                date_from=date_from,
                date_to=date_to,
                status=SxStandardCostSheet.STATUS_DRAFT,
                notes=notes or "",
                is_demo=False,
            )

    docs = ProductTechDoc.objects.filter(is_active=True).order_by("product_code")
    if product_codes:
        allowed = [(c or "").strip() for c in product_codes if (c or "").strip()]
        docs = docs.filter(product_code__in=allowed)

    create_lines: list[SxStandardCostLine] = []
    seen: set[str] = set()
    for doc in docs:
        code_key = (doc.product_code or "").strip().upper()
        if code_key in seen:
            continue
        bom = get_active_bom(doc)
        if not bom:
            bom = get_working_bom(doc)
        if not bom:
            continue
        result = compute_costing(bom)
        seen.add(code_key)
        create_lines.append(
            SxStandardCostLine(
                sheet=sheet,
                product_code=doc.product_code,
                product_name=result.product_name or doc.product_name or "",
                unit_cost=result.total_cost,
                material_cost=result.material_cost,
                labor_cost=result.labor_cost,
                overhead_cost=result.overhead_cost,
            )
        )

    if not create_lines:
        raise PlanCostingError("Không có SP nào có BOM để tính giá thành.")
    SxStandardCostLine.objects.bulk_create(create_lines)
    return sheet


@transaction.atomic
def confirm_standard_sheet(*, sheet_id: int) -> SxStandardCostSheet:
    sheet = SxStandardCostSheet.objects.select_for_update().prefetch_related("lines").get(pk=sheet_id)
    if sheet.status != SxStandardCostSheet.STATUS_DRAFT:
        raise PlanCostingError("Bảng GT đã chốt hoặc không ở trạng thái nháp.")
    if not sheet.lines.exists():
        raise PlanCostingError("Bảng GT phải có ít nhất một dòng SP.")
    sheet.status = SxStandardCostSheet.STATUS_CONFIRMED
    sheet.save(update_fields=["status"])
    return sheet


def resolve_unit_standard_cost(
    product_code: str,
    *,
    standard_sheet_id: int | None = None,
) -> Decimal:
    from san_xuat.models import ProductTechDoc

    code = (product_code or "").strip()
    if not code:
        return Decimal("0")

    sheet_qs = SxStandardCostSheet.objects.filter(
        is_demo=False,
        status=SxStandardCostSheet.STATUS_CONFIRMED,
    ).order_by("-date_from", "-pk")
    if standard_sheet_id:
        sheet_qs = sheet_qs.filter(pk=standard_sheet_id)

    for sheet in sheet_qs[:5]:
        line = sheet.lines.filter(product_code__iexact=code).first()
        if line and line.unit_cost:
            return line.unit_cost

    doc = ProductTechDoc.objects.filter(product_code__iexact=code, is_active=True).first()
    if not doc:
        return Decimal("0")
    bom = get_active_bom(doc) or get_working_bom(doc)
    if not bom:
        return Decimal("0")
    return compute_costing(bom).total_cost


@transaction.atomic
def build_order_sheet_from_kv(
    *,
    name: str,
    date_from,
    date_to,
    kv_order_kiotviet_id: int | None = None,
    kv_order_code: str = "",
    standard_sheet_id: int | None = None,
    code: str | None = None,
    notes: str = "",
    sheet_id: int | None = None,
) -> "SxOrderPlanCost":
    from kiotviet.models import KvOrder, KvOrderLine
    from kiotviet.sync_service import current_retailer
    from san_xuat.hub_models import SxOrderPlanCost, SxOrderPlanCostLine

    if date_from > date_to:
        raise PlanCostingError("Kỳ giá thành không hợp lệ (từ ngày > đến ngày).")

    retailer = current_retailer()
    order = None
    if kv_order_kiotviet_id:
        order = KvOrder.objects.filter(
            retailer=retailer,
            kiotviet_id=kv_order_kiotviet_id,
            is_deleted=False,
        ).first()
    if not order and (kv_order_code or "").strip():
        order = (
            KvOrder.objects.filter(
                retailer=retailer,
                code__iexact=kv_order_code.strip(),
                is_deleted=False,
            )
            .order_by("-purchase_date", "-id")
            .first()
        )
    if not order:
        raise PlanCostingError("Không tìm thấy đơn KV trong dữ liệu đã sync.")

    kv_lines = KvOrderLine.objects.filter(
        retailer=retailer,
        order_kiotviet_id=order.kiotviet_id,
    ).order_by("line_index", "id")
    if not kv_lines.exists():
        raise PlanCostingError("Đơn KV không có dòng hàng.")

    if sheet_id:
        sheet = SxOrderPlanCost.objects.select_for_update().prefetch_related(
            "lines__typed_extras__cost_type",
        ).get(pk=sheet_id)
        if sheet.status != SxOrderPlanCost.STATUS_DRAFT:
            raise PlanCostingError("Chỉ cập nhật bảng GTĐH ở trạng thái nháp.")
        preserved_extras = {
            (line.product_code or "").strip().upper(): line.extra_cost or Decimal("0")
            for line in sheet.lines.all()
        }
        preserved_typed: dict[str, dict[str, Decimal]] = {}
        for line in sheet.lines.all():
            key = (line.product_code or "").strip().upper()
            preserved_typed[key] = {
                (ex.cost_type.code or "").strip().upper(): ex.amount or Decimal("0")
                for ex in line.typed_extras.all()
            }
        sheet.lines.all().delete()
        sheet.name = (name or "").strip() or sheet.name
        sheet.date_from = date_from
        sheet.date_to = date_to
        sheet.kv_order_code = order.code or ""
        sheet.kv_order_kiotviet_id = order.kiotviet_id
        sheet.notes = notes or sheet.notes
        sheet.save(
            update_fields=["name", "date_from", "date_to", "kv_order_code", "kv_order_kiotviet_id", "notes"],
        )
    else:
        preserved_extras = {}
        preserved_typed = {}
        sheet = SxOrderPlanCost.objects.create(
            code=_code("cost_order", SxOrderPlanCost, code=code),
            name=(name or "").strip() or f"GTKH đơn {order.code or order.kiotviet_id}",
            kv_order_code=order.code or "",
            kv_order_kiotviet_id=order.kiotviet_id,
            date_from=date_from,
            date_to=date_to,
            status=SxOrderPlanCost.STATUS_DRAFT,
            total_cost=Decimal("0"),
            notes=notes or "",
            is_demo=False,
        )

    create_lines: list[SxOrderPlanCostLine] = []
    total = Decimal("0")
    for kv_line in kv_lines:
        product_code = (kv_line.product_code or "").strip()
        qty = Decimal(str(kv_line.quantity or 0)).quantize(Decimal("0.01"))
        if not product_code or qty <= 0:
            continue
        unit_cost = resolve_unit_standard_cost(
            product_code,
            standard_sheet_id=standard_sheet_id,
        ).quantize(Decimal("0.01"))
        typed = preserved_typed.get(product_code.upper(), {})
        if typed:
            extra_cost = sum(typed.values(), Decimal("0")).quantize(Decimal("0.01"))
        else:
            extra_cost = preserved_extras.get(product_code.upper(), Decimal("0"))
        line_cost = (unit_cost * qty + extra_cost).quantize(Decimal("0.01"))
        total += line_cost
        create_lines.append(
            SxOrderPlanCostLine(
                sheet=sheet,
                product_code=product_code,
                product_name=(kv_line.product_name or "").strip(),
                qty=qty,
                unit_cost=unit_cost,
                extra_cost=extra_cost,
                line_cost=line_cost,
            )
        )

    if not create_lines:
        raise PlanCostingError("Không có dòng hàng hợp lệ để tính GTKH.")
    SxOrderPlanCostLine.objects.bulk_create(create_lines)

    if preserved_typed:
        from san_xuat.hub_models import SxCostType, SxOrderPlanCostLineExtra

        type_by_code = {
            (ct.code or "").strip().upper(): ct
            for ct in SxCostType.objects.filter(is_demo=False)
        }
        extras_to_create: list[SxOrderPlanCostLineExtra] = []
        for line in sheet.lines.all():
            typed = preserved_typed.get((line.product_code or "").strip().upper(), {})
            for type_code, amount in typed.items():
                ct = type_by_code.get(type_code)
                if not ct or amount is None:
                    continue
                extras_to_create.append(
                    SxOrderPlanCostLineExtra(
                        line=line,
                        cost_type=ct,
                        amount=Decimal(str(amount)).quantize(Decimal("0.01")),
                    )
                )
        if extras_to_create:
            SxOrderPlanCostLineExtra.objects.bulk_create(extras_to_create)

    sheet.total_cost = total.quantize(Decimal("0.01"))
    sheet.save(update_fields=["total_cost"])
    return sheet


@transaction.atomic
def confirm_order_plan_cost(*, sheet_id: int) -> "SxOrderPlanCost":
    from san_xuat.hub_models import SxOrderPlanCost

    sheet = SxOrderPlanCost.objects.select_for_update().prefetch_related("lines").get(pk=sheet_id)
    if sheet.status != SxOrderPlanCost.STATUS_DRAFT:
        raise PlanCostingError("Bảng GTĐH đã chốt hoặc không ở trạng thái nháp.")
    if not sheet.lines.exists():
        raise PlanCostingError("Bảng GTĐH phải có ít nhất một dòng SP.")
    sheet.status = SxOrderPlanCost.STATUS_CONFIRMED
    sheet.save(update_fields=["status"])
    return sheet


def _recalc_order_sheet_total(sheet) -> Decimal:
    total = sum((line.line_cost or Decimal("0") for line in sheet.lines.all()), Decimal("0"))
    return total.quantize(Decimal("0.01"))


@transaction.atomic
def update_order_plan_extra_costs(
    *,
    sheet_id: int,
    extras: dict[int, Decimal],
) -> "SxOrderPlanCost":
    """C3 compat: gán tổng CP thêm vào loại mặc định CP_KHAC (nếu có)."""
    from san_xuat.hub_models import SxCostType, SxOrderPlanCost, SxOrderPlanCostLineExtra

    sheet = SxOrderPlanCost.objects.select_for_update().prefetch_related("lines").get(pk=sheet_id)
    if sheet.status != SxOrderPlanCost.STATUS_DRAFT:
        raise PlanCostingError("Chỉ sửa chi phí thêm khi bảng GTĐH ở trạng thái nháp.")

    default_type = (
        SxCostType.objects.filter(is_demo=False, is_active=True, code__iexact="CP_KHAC").first()
        or SxCostType.objects.filter(is_demo=False, is_active=True).order_by("sort_order", "pk").first()
    )

    for line in sheet.lines.all():
        extra = extras.get(line.pk, line.extra_cost or Decimal("0"))
        if extra < 0:
            raise PlanCostingError(f"Chi phí thêm không âm: {line.product_code}.")
        extra = extra.quantize(Decimal("0.01"))
        line.extra_cost = extra
        line.line_cost = ((line.qty or Decimal("0")) * (line.unit_cost or Decimal("0")) + extra).quantize(
            Decimal("0.01"),
        )
        line.save(update_fields=["extra_cost", "line_cost"])
        if default_type:
            SxOrderPlanCostLineExtra.objects.update_or_create(
                line=line,
                cost_type=default_type,
                defaults={"amount": extra},
            )

    sheet.total_cost = _recalc_order_sheet_total(sheet)
    sheet.save(update_fields=["total_cost"])
    return sheet


def ensure_default_cost_types() -> list:
    from san_xuat.hub_models import SxCostType

    defaults = [
        ("CP_VC", "Vận chuyển", 10),
        ("CP_GC", "Gia công ngoài", 20),
        ("CP_KHAC", "Chi phí khác", 90),
    ]
    created = []
    for code, name, sort_order in defaults:
        obj, was_created = SxCostType.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "sort_order": sort_order,
                "is_active": True,
                "is_demo": False,
            },
        )
        if was_created:
            created.append(obj)
    return created


def list_active_cost_types():
    from san_xuat.hub_models import SxCostType

    ensure_default_cost_types()
    return list(
        SxCostType.objects.filter(is_demo=False, is_active=True).order_by("sort_order", "code")
    )


@transaction.atomic
def upsert_cost_type(
    *,
    code: str,
    name: str,
    sort_order: int = 100,
    is_active: bool = True,
    notes: str = "",
    cost_type_id: int | None = None,
):
    from san_xuat.hub_models import SxCostType

    code = (code or "").strip().upper()
    name = (name or "").strip()
    if not code or not name:
        raise PlanCostingError("Mã và tên loại chi phí là bắt buộc.")
    if cost_type_id:
        ct = SxCostType.objects.select_for_update().get(pk=cost_type_id)
        if SxCostType.objects.filter(code__iexact=code).exclude(pk=ct.pk).exists():
            raise PlanCostingError(f"Mã loại CP đã tồn tại: {code}")
        ct.code = code
        ct.name = name
        ct.sort_order = sort_order
        ct.is_active = is_active
        ct.notes = notes or ""
        ct.save(update_fields=["code", "name", "sort_order", "is_active", "notes"])
        return ct
    if SxCostType.objects.filter(code__iexact=code).exists():
        raise PlanCostingError(f"Mã loại CP đã tồn tại: {code}")
    return SxCostType.objects.create(
        code=code,
        name=name,
        sort_order=sort_order,
        is_active=is_active,
        notes=notes or "",
        is_demo=False,
    )


@transaction.atomic
def update_order_plan_typed_extras(
    *,
    sheet_id: int,
    extras: dict[int, dict[int, Decimal]],
) -> "SxOrderPlanCost":
    """extras: {line_id: {cost_type_id: amount}}."""
    from san_xuat.hub_models import SxCostType, SxOrderPlanCost, SxOrderPlanCostLineExtra

    sheet = (
        SxOrderPlanCost.objects.select_for_update()
        .prefetch_related("lines")
        .get(pk=sheet_id)
    )
    if sheet.status != SxOrderPlanCost.STATUS_DRAFT:
        raise PlanCostingError("Chỉ sửa chi phí thêm khi bảng GTĐH ở trạng thái nháp.")

    active_types = {
        ct.pk: ct
        for ct in SxCostType.objects.filter(is_demo=False, is_active=True)
    }
    if not active_types:
        ensure_default_cost_types()
        active_types = {
            ct.pk: ct
            for ct in SxCostType.objects.filter(is_demo=False, is_active=True)
        }

    for line in sheet.lines.all():
        by_type = extras.get(line.pk, {})
        for type_id, amount in by_type.items():
            if type_id not in active_types:
                continue
            if amount is None:
                amount = Decimal("0")
            if amount < 0:
                raise PlanCostingError(
                    f"Chi phí thêm không âm: {line.product_code} / {active_types[type_id].code}."
                )
            amount = Decimal(str(amount)).quantize(Decimal("0.01"))
            if amount == 0:
                SxOrderPlanCostLineExtra.objects.filter(line=line, cost_type_id=type_id).delete()
            else:
                SxOrderPlanCostLineExtra.objects.update_or_create(
                    line=line,
                    cost_type_id=type_id,
                    defaults={"amount": amount},
                )
        total_extra = sum(
            (
                ex.amount or Decimal("0")
                for ex in SxOrderPlanCostLineExtra.objects.filter(
                    line=line, cost_type__is_active=True,
                )
            ),
            Decimal("0"),
        ).quantize(Decimal("0.01"))
        line.extra_cost = total_extra
        line.line_cost = (
            (line.qty or Decimal("0")) * (line.unit_cost or Decimal("0")) + total_extra
        ).quantize(Decimal("0.01"))
        line.save(update_fields=["extra_cost", "line_cost"])

    sheet.total_cost = _recalc_order_sheet_total(sheet)
    sheet.save(update_fields=["total_cost"])
    return sheet
