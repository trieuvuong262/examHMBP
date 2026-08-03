"""Views vận hành nhà máy: shop floor, NCR, GT thực, downtime/OEE, catalog, staging."""

from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from assessment.decorators import module_perm_required
from hrm.module_permissions import MODULE_SAN_XUAT
from kho_npl.models import Material, StockReservation, Unit, WarehouseLocation
from san_xuat.hub_models import (
    SxActualCostSheet,
    SxDowntimeEvent,
    SxNcrCase,
    SxProductGroup,
    SxProductionOrder,
    SxQcAlert,
    SxTeamHrMap,
    SxWorkCenter,
)
from san_xuat.list_filters import (
    SX_FILTER_ACTUAL_COST,
    SX_FILTER_CATALOG_ITEM,
    SX_FILTER_CATALOG_MATERIAL,
    SX_FILTER_DOWNTIME,
    SX_FILTER_NCR,
    SX_FILTER_TEAM_HR,
    SX_FILTER_TECH_DOC,
    apply_sx_list_filters,
    parse_sx_list_filters,
    prepare_hub_list,
    resolve_sx_period,
    sx_filter_context,
)
from san_xuat.models import ProductTechDoc
from san_xuat.services.actual_costing import (
    ActualCostError,
    compute_actual_cost_for_mo,
    create_or_refresh_actual_cost,
)
from san_xuat.services.ncr import NcrError, confirm_ncr, create_ncr_from_alert
from san_xuat.services.shopfloor import ShopFloorError, quick_confirm_scan
from san_xuat.views_hub import _perm_ctx


def _next_dt_code() -> str:
    from san_xuat.services.sx_settings import sx_prefix

    year = timezone.localdate().year
    prefix = f"{sx_prefix('downtime')}-{year}-"
    last = (
        SxDowntimeEvent.objects.filter(code__startswith=prefix)
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


@module_perm_required(MODULE_SAN_XUAT, "view")
def shop_floor(request):
    result = None
    can_update = _perm_ctx(request).get("can_update")
    if request.method == "POST" and can_update:
        scan = (request.POST.get("scan") or "").strip()
        process_name = (request.POST.get("process_name") or "").strip()
        team_label = (request.POST.get("team_label") or "").strip()
        try:
            qty = Decimal((request.POST.get("qty_good") or "1").replace(",", "."))
        except (InvalidOperation, ValueError):
            qty = Decimal("1")
        try:
            result = quick_confirm_scan(
                scan=scan,
                process_name=process_name,
                qty_good=qty,
                team_label=team_label,
            )
            messages.success(
                request,
                f"Đã xác nhận {result['stat'].code} · Lệnh sản xuất {result['mo'].code}",
            )
        except ShopFloorError as exc:
            messages.error(request, str(exc))
    mos = (
        SxProductionOrder.objects.filter(
            is_demo=False,
            status__in=(
                SxProductionOrder.STATUS_RELEASED,
                SxProductionOrder.STATUS_IN_PROGRESS,
            ),
        )
        .order_by("-order_date")[:30]
    )
    return render(
        request,
        "san_xuat/shop_floor.html",
        {**_perm_ctx(request), "result": result, "mos": mos},
    )


@module_perm_required(MODULE_SAN_XUAT, "view")
def ncr_list(request):
    base_qs = SxNcrCase.objects.filter(is_demo=False).select_related(
        "production_order", "alert", "remake_order"
    ).order_by("-created_at", "-pk")
    cases, fctx = prepare_hub_list(request, base_qs, SX_FILTER_NCR, list_key='ncr')
    return render(
        request,
        "san_xuat/ncr_list.html",
        {**_perm_ctx(request), "cases": cases, **fctx},
    )


@module_perm_required(MODULE_SAN_XUAT, "view")
def ncr_detail(request, pk: int):
    case = get_object_or_404(
        SxNcrCase.objects.select_related(
            "production_order", "alert", "remake_order", "rework_stat"
        ),
        pk=pk,
    )
    can_update = _perm_ctx(request).get("can_update")
    if request.method == "POST" and can_update:
        action = (request.POST.get("action") or "").strip()
        if action == "confirm" and case.status == SxNcrCase.STATUS_DRAFT:
            try:
                case = confirm_ncr(ncr_id=case.pk, user=request.user)
            except NcrError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f"Đã xác nhận phiếu xử lý hàng không đạt {case.code}.")
                return redirect("san_xuat:ncr_detail", pk=case.pk)
    return render(
        request,
        "san_xuat/ncr_detail.html",
        {**_perm_ctx(request), "case": case, "can_update": can_update},
    )


@module_perm_required(MODULE_SAN_XUAT, "view")
def actual_cost_list(request):
    base_qs = (
        SxActualCostSheet.objects.filter(is_demo=False)
        .select_related("production_order")
        .order_by("-created_at")
    )
    sheets, fctx = prepare_hub_list(request, base_qs, SX_FILTER_ACTUAL_COST, list_key='actual_cost')
    return render(
        request,
        "san_xuat/actual_cost_list.html",
        {**_perm_ctx(request), "sheets": sheets, **fctx},
    )


@module_perm_required(MODULE_SAN_XUAT, "view")
def actual_cost_mo(request, mo_id: int):
    mo = get_object_or_404(SxProductionOrder, pk=mo_id)
    br = compute_actual_cost_for_mo(production_order_id=mo.pk)
    sheet = (
        SxActualCostSheet.objects.filter(production_order=mo, is_demo=False)
        .order_by("-pk")
        .first()
    )
    can_update = _perm_ctx(request).get("can_update")
    if request.method == "POST" and can_update:
        action = (request.POST.get("action") or "").strip()
        try:
            if action == "refresh":
                sheet = create_or_refresh_actual_cost(production_order_id=mo.pk, close=False)
                messages.success(request, f"Đã tính lại {sheet.code}.")
            elif action == "close":
                sheet = create_or_refresh_actual_cost(production_order_id=mo.pk, close=True)
                messages.success(request, f"Đã chốt {sheet.code}.")
            return redirect("san_xuat:actual_cost_mo", mo_id=mo.pk)
        except ActualCostError as exc:
            messages.error(request, str(exc))
    return render(
        request,
        "san_xuat/actual_cost_mo.html",
        {
            **_perm_ctx(request),
            "mo": mo,
            "br": br,
            "sheet": sheet,
            "can_update": can_update,
        },
    )


@module_perm_required(MODULE_SAN_XUAT, "view")
def downtime_list(request):
    base_qs = SxDowntimeEvent.objects.filter(is_demo=False).select_related(
        "work_center", "production_order"
    ).order_by("-event_date", "-pk")
    events, fctx = prepare_hub_list(request, base_qs, SX_FILTER_DOWNTIME, list_key='downtime')
    can_create = _perm_ctx(request).get("can_create")
    if request.method == "POST" and can_create:
        reason = (request.POST.get("reason") or "").strip()
        try:
            minutes = int(request.POST.get("minutes") or "0")
        except ValueError:
            minutes = 0
        wc_id = (request.POST.get("work_center") or "").strip()
        mo_id = (request.POST.get("production_order") or "").strip()
        if reason and minutes > 0:
            SxDowntimeEvent.objects.create(
                code=_next_dt_code(),
                work_center_id=int(wc_id) if wc_id.isdigit() else None,
                production_order_id=int(mo_id) if mo_id.isdigit() else None,
                team_label=(request.POST.get("team_label") or "").strip(),
                event_date=timezone.localdate(),
                reason=reason,
                minutes=minutes,
                notes=(request.POST.get("notes") or "").strip(),
                is_demo=False,
            )
            messages.success(request, "Đã ghi nhận dừng chuyền.")
            return redirect("san_xuat:downtime_list")
        messages.error(request, "Cần lý do và số phút > 0.")

    # OEE đầy đủ: Sẵn sàng × Hiệu suất × Chất lượng
    from san_xuat.services.oee import build_oee_rows

    centers = list(SxWorkCenter.objects.filter(is_active=True, is_demo=False))
    today = timezone.localdate()
    oee_from = _parse_oee_date(request.GET.get("oee_from")) or today.replace(day=1)
    oee_to = _parse_oee_date(request.GET.get("oee_to")) or today
    if oee_from > oee_to:
        oee_from, oee_to = oee_to, oee_from
    oee = build_oee_rows(date_from=oee_from, date_to=oee_to)

    return render(
        request,
        "san_xuat/downtime_list.html",
        {
            **_perm_ctx(request),
            "events": events,
            "centers": centers,
            "mos": SxProductionOrder.objects.filter(is_demo=False).order_by("-order_date")[:50],
            "oee": oee,
            "oee_rows": oee["rows"],
            "oee_total": oee["total"],
            "oee_from": oee_from,
            "oee_to": oee_to,
            "oee_shift_hours": oee["shift_hours"],
            "can_create": can_create,
            **fctx,
        },
    )


def _parse_oee_date(raw: str | None):
    from datetime import date as _date

    text = (raw or "").strip()
    if not text:
        return None
    try:
        return _date.fromisoformat(text)
    except ValueError:
        return None


@module_perm_required(MODULE_SAN_XUAT, "view")
def unified_catalog(request):
    filters = parse_sx_list_filters(request)
    groups = SxProductGroup.objects.filter(is_active=True, is_demo=False).select_related('created_by')
    docs = ProductTechDoc.objects.select_related('created_by').all().order_by("product_code")
    materials = Material.objects.filter(is_active=True).select_related("unit", "category")
    units = Unit.objects.filter(is_active=True).order_by("code")
    docs = apply_sx_list_filters(docs, filters, SX_FILTER_TECH_DOC)
    materials = apply_sx_list_filters(materials, filters, SX_FILTER_CATALOG_MATERIAL)
    groups = apply_sx_list_filters(groups, filters, SX_FILTER_CATALOG_ITEM)
    can_create = _perm_ctx(request).get("can_create")
    if request.method == "POST" and can_create:
        code = (request.POST.get("group_code") or "").strip().upper()
        name = (request.POST.get("group_name") or "").strip()
        if code and name:
            SxProductGroup.objects.get_or_create(
                code=code,
                defaults={"name": name, "is_demo": False, "created_by": request.user},
            )
            messages.success(request, f"Đã thêm nhóm SP {code}.")
            return redirect("san_xuat:unified_catalog")
        messages.error(request, "Cần mã và tên nhóm.")
    return render(
        request,
        "san_xuat/unified_catalog.html",
        {
            **_perm_ctx(request),
            "groups": groups[:100],
            "docs": docs[:100],
            "materials": materials[:100],
            "units": units[:100],
            "can_create": can_create,
            **sx_filter_context(filters),
        },
    )


@module_perm_required(MODULE_SAN_XUAT, "view")
def staging_locations(request):
    locs = WarehouseLocation.objects.filter(is_active=True).order_by("location_kind", "code")
    can_update = _perm_ctx(request).get("can_update")
    if request.method == "POST" and can_update:
        loc_id = (request.POST.get("location_id") or "").strip()
        kind = (request.POST.get("location_kind") or "").strip()
        if loc_id.isdigit() and kind in dict(WarehouseLocation.KIND_CHOICES):
            WarehouseLocation.objects.filter(pk=int(loc_id)).update(location_kind=kind)
            messages.success(request, "Đã cập nhật loại vị trí.")
            return redirect("san_xuat:staging_locations")
    reservations = (
        StockReservation.objects.filter(status=StockReservation.STATUS_ACTIVE)
        .select_related("material", "location")
        .order_by("-created_at")[:100]
    )
    return render(
        request,
        "san_xuat/staging_locations.html",
        {
            **_perm_ctx(request),
            "locations": locs,
            "kinds": WarehouseLocation.KIND_CHOICES,
            "reservations": reservations,
            "can_update": can_update,
        },
    )


@module_perm_required(MODULE_SAN_XUAT, "export")
def piece_rate_hr_export(request):
    """CSV lương SP để HR/payroll import — ưu tiên mã NV từ SxTeamHrMap."""
    from san_xuat.services.phase3 import compute_piece_rate_pay

    date_from, date_to, _filters = resolve_sx_period(request)
    rows = compute_piece_rate_pay(date_from=date_from, date_to=date_to)
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="luong-san-pham-hr.csv"'
    resp.write("\ufeff")
    w = csv.writer(resp)
    w.writerow(
        [
            "Ky_tu",
            "Ky_den",
            "Ma_NV",
            "Ten_NV",
            "To_nhan_vien",
            "Cong_doan",
            "LSX",
            "TKSX",
            "SL_dat",
            "Don_gia",
            "Thanh_tien",
            "Da_map_HR",
            "Ghi_chu_HR",
        ]
    )
    for r in rows:
        w.writerow(
            [
                date_from.isoformat(),
                date_to.isoformat(),
                r.employee_code or "",
                r.employee_name or "",
                r.team_label,
                r.process_name,
                r.production_order_code,
                r.stat_code,
                str(r.qty_good),
                str(r.piece_rate),
                str(r.amount),
                "1" if r.hr_mapped else "0",
                "" if r.hr_mapped else "Chưa map tổ → mã NV (xem /san-xuat/luong-san-pham/map-hr/)",
            ]
        )
    return resp


@module_perm_required(MODULE_SAN_XUAT, "view")
def team_hr_map(request):
    """Map nhãn tổ TKSX → mã NV để xuất lương SP."""
    from san_xuat.hub_models import SxTeamHrMap

    can_create = _perm_ctx(request).get("can_create")
    can_update = _perm_ctx(request).get("can_update")
    if request.method == "POST" and (can_create or can_update):
        team = (request.POST.get("team_label") or "").strip()
        code = (request.POST.get("employee_code") or "").strip()
        name = (request.POST.get("employee_name") or "").strip()
        if team and code:
            obj, created = SxTeamHrMap.objects.update_or_create(
                team_label=team,
                defaults={
                    "employee_code": code,
                    "employee_name": name,
                    "is_active": True,
                    "is_demo": False,
                },
            )
            messages.success(
                request,
                f"{'Đã thêm' if created else 'Đã cập nhật'} map «{obj.team_label}» → {obj.employee_code}.",
            )
            return redirect("san_xuat:team_hr_map")
        messages.error(request, "Cần nhãn tổ và mã nhân viên.")
    base_qs = SxTeamHrMap.objects.filter(is_demo=False).order_by("team_label")
    maps, fctx = prepare_hub_list(request, base_qs, SX_FILTER_TEAM_HR, list_key='team_hr')
    return render(
        request,
        "san_xuat/team_hr_map.html",
        {
            **_perm_ctx(request),
            "maps": maps,
            "can_create": can_create,
            "can_update": can_update,
            **fctx,
        },
    )
