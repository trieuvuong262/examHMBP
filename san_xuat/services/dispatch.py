"""Điều phối SX: Lệnh sản xuất -> Yêu cầu xuất (explode BOM) -> duyệt -> StockIssue (kho_npl).

Đây là service lõi cho D0/D1 theo `docs/san_xuat/dieu-phoi.md`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db import models as dj_models
from django.db import transaction
from django.utils import timezone

from kho_npl.choices import DOC_STATUS_POSTED, ISSUE_TYPE_PRODUCTION
from kho_npl.models import (
    Material,
    MaterialBatch,
    WarehouseLocation,
    StockIssue,
    StockIssueLine,
    StockBalance,
)
from kho_npl.services.batches import BatchWorkflowError, batches_with_stock
from kho_npl.services.doc_numbers import next_issue_number
from kho_npl.services.issues import IssueWorkflowError, post_stock_issue

from san_xuat.models import BomLine, ProductTechDoc
from san_xuat.hub_models import (
    SxDetailPlan,
    SxDisassemblyOrder,
    SxFgReceiptRequest,
    SxMaterialIssueRequest,
    SxMaterialIssueRequestLine,
    SxNplSurplus,
    SxOverallPlan,
    SxProductionOrder,
    SxProductionStat,
    SxQcAlert,
    SxWipBalance,
    SxWipHandover,
    SxWipReturn,
)
from san_xuat.services.bom import get_working_bom, activate_bom
from san_xuat.services.sx_settings import sx_prefix


class DispatchError(Exception):
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
        n = int(str(latest).rsplit("-", 1)[-1])
    except ValueError:
        n = 0
    return f"{base}{n + 1:04d}"


def _code(kind: str, model, *, code: str | None = None, field: str = "code", fallback: str | None = None):
    raw = (code or "").strip()
    if raw:
        return raw
    return _next_code(sx_prefix(kind, fallback), model, field=field)


def _resolve_material_by_code(code: str) -> Material:
    raw = (code or "").strip()
    if not raw:
        raise DispatchError("Thiếu mã NPL.")
    mat = Material.objects.filter(code__iexact=raw, is_active=True).first()
    if not mat:
        raise DispatchError(f"NPL không tồn tại hoặc không hoạt động: {raw}")
    return mat


def _resolve_stock_location(
    material: Material,
    qty_needed: Decimal,
    *,
    preferred: WarehouseLocation | None = None,
) -> WarehouseLocation:
    """Chọn một vị trí đủ qty (ưu tiên preferred nếu đủ)."""
    if preferred and preferred.is_active:
        bal = StockBalance.objects.filter(material=material, location=preferred).first()
        available = bal.quantity if bal else Decimal("0")
        if available >= qty_needed:
            return preferred
    locs = WarehouseLocation.objects.filter(is_active=True).order_by("code")
    for loc in locs:
        bal = StockBalance.objects.filter(material=material, location=loc).first()
        available = bal.quantity if bal else Decimal("0")
        if available >= qty_needed:
            return loc
    raise DispatchError(
        f"Không đủ tồn kho cho {material.code}: cần {qty_needed}, không có vị trí nào đủ."
    )


def _split_stock_locations(
    material: Material,
    qty_needed: Decimal,
    *,
    preferred: WarehouseLocation | None = None,
) -> list[tuple[WarehouseLocation, Decimal]]:
    """Chia qty_needed theo nhiều vị trí (ưu tiên preferred, rồi theo mã vị trí)."""
    remaining = (qty_needed or Decimal("0")).quantize(Decimal("0.001"))
    if remaining <= 0:
        return []
    splits: list[tuple[WarehouseLocation, Decimal]] = []
    seen: set[int] = set()

    def _take(loc: WarehouseLocation) -> None:
        nonlocal remaining
        if remaining <= 0 or loc.pk in seen:
            return
        seen.add(loc.pk)
        bal = StockBalance.objects.filter(material=material, location=loc).first()
        available = (bal.quantity if bal else Decimal("0")).quantize(Decimal("0.001"))
        if available <= 0:
            return
        take = available if available < remaining else remaining
        if take > 0:
            splits.append((loc, take))
            remaining -= take

    if preferred and preferred.is_active:
        _take(preferred)
    for loc in WarehouseLocation.objects.filter(is_active=True).order_by("code"):
        _take(loc)
    if remaining > 0:
        raise DispatchError(
            f"Không đủ tồn kho cho {material.code}: thiếu {remaining} (cần {qty_needed})."
        )
    return splits


def _allocate_batches(material: Material, qty_needed: Decimal) -> list[tuple[MaterialBatch, Decimal]]:
    """Phân bổ qty_needed theo các lô còn tồn (chia nhiều batch nếu cần)."""
    remaining = qty_needed
    allocations: list[tuple[MaterialBatch, Decimal]] = []
    for batch in batches_with_stock(material, include_zero=False):
        if remaining <= 0:
            break
        if batch.quantity <= 0:
            continue
        take = batch.quantity if batch.quantity < remaining else remaining
        if take > 0:
            allocations.append((batch, take))
            remaining -= take
    if remaining > 0:
        raise DispatchError(
            f"Không đủ tồn theo lô cho {material.code}: thiếu {remaining} (cần {qty_needed})."
        )
    return allocations


@transaction.atomic
def create_mo_from_bom(
    *,
    product_code: str,
    qty: Decimal,
    code: str | None = None,
    order_date=None,
    due_date=None,
    planned_start=None,
    planned_end=None,
    team_label: str = "",
    process_name: str = "",
    notes: str = "",
    user=None,
    detail_plan_id: int | None = None,
    is_sample: bool = False,
) -> SxProductionOrder:
    product_code = (product_code or "").strip()
    if not product_code:
        raise DispatchError("Thiếu mã sản phẩm.")
    if qty is None or qty <= 0:
        raise DispatchError("SL phải > 0.")

    tech_doc = ProductTechDoc.objects.filter(product_code__iexact=product_code).first()
    if not tech_doc:
        raise DispatchError(f"Chưa có hồ sơ SX cho mã {product_code}.")

    working_bom = get_working_bom(tech_doc)
    if not working_bom:
        raise DispatchError(f"Mã {product_code} chưa có BOM để tính.")

    mo_code = _code("mo", SxProductionOrder, code=code)

    mo = SxProductionOrder.objects.create(
        code=mo_code,
        product_code=tech_doc.product_code,
        product_name=tech_doc.product_name or "",
        bom_version=working_bom,
        qty=qty,
        qty_done=Decimal("0"),
        order_date=order_date or timezone.localdate(),
        due_date=due_date,
        planned_start=planned_start,
        planned_end=planned_end,
        team_label=team_label or "",
        process_name=(process_name or "").strip(),
        status=SxProductionOrder.STATUS_DRAFT,
        notes=notes or "",
        detail_plan_id=detail_plan_id,
        is_sample=bool(is_sample),
        created_by=user,
    )
    return mo


@transaction.atomic
def mo_release(*, mo_id: int, user) -> SxProductionOrder:
    # Tránh `select_related()` trong query có `select_for_update()` khi quan hệ có thể nullable
    # (Postgres không cho FOR UPDATE trên nullable side của outer join).
    mo = SxProductionOrder.objects.select_for_update().get(pk=mo_id)
    if mo.status != SxProductionOrder.STATUS_DRAFT:
        raise DispatchError("Chỉ Lệnh sản xuất trạng thái Nháp mới được release.")
    if not mo.bom_version_id:
        raise DispatchError("Lệnh sản xuất chưa gắn BOM.")

    # Đảm bảo BOM gắn vào MO là BOM active (archive BOM active khác nếu cần).
    activate_bom(mo.bom_version)

    mo.status = SxProductionOrder.STATUS_RELEASED
    mo.save(update_fields=["status"])
    return mo


@transaction.atomic
def build_material_issue_request(
    *, production_order_id: int, code: str | None = None, user=None, notes: str = ""
) -> SxMaterialIssueRequest:
    mo = (
        SxProductionOrder.objects.select_for_update()
        .prefetch_related("bom_version__lines__material")
        .get(pk=production_order_id)
    )
    if mo.status not in (SxProductionOrder.STATUS_RELEASED, SxProductionOrder.STATUS_IN_PROGRESS, SxProductionOrder.STATUS_DONE):
        raise DispatchError("Chỉ được tạo Yêu cầu xuất khi Lệnh sản xuất đã release.")
    if not mo.bom_version_id:
        raise DispatchError("Lệnh sản xuất chưa có BOM.")

    req_code = _code("ycx", SxMaterialIssueRequest, code=code)
    req = SxMaterialIssueRequest.objects.create(
        code=req_code,
        production_order=mo,
        status="draft",
        request_date=timezone.localdate(),
        notes=notes or "",
    )

    # Explode BOM: qty_requested = BOM.qty_with_scrap × MO.qty (NVL thay thế nếu tồn chính thiếu)
    lines = []
    for bom_line in mo.bom_version.lines.select_related("material", "substitute_material").all():
        assert isinstance(bom_line, BomLine)
        qty_requested = (bom_line.qty_with_scrap * (mo.qty or Decimal("0"))).quantize(Decimal("0.001"))
        material = bom_line.resolve_issue_material(needed_qty=qty_requested)
        lines.append(
            SxMaterialIssueRequestLine(
                request=req,
                material_code=material.code,
                material_name=material.name,
                qty_requested=qty_requested,
                qty_issued=Decimal("0"),
            )
        )
    SxMaterialIssueRequestLine.objects.bulk_create(lines)
    from san_xuat.services.sx_settings import sx_bool

    if sx_bool("ycx_auto_reserve_stock", True):
        from kho_npl.services.reservation import upsert_reservations_for_ycx

        upsert_reservations_for_ycx(request=req)
    return req


@dataclass(frozen=True)
class ApprovedIssueResult:
    request: SxMaterialIssueRequest
    stock_issue: StockIssue


def _recompute_mo_progress(mo: SxProductionOrder) -> SxProductionOrder:
    from san_xuat.services.gates import check_packing_before_done

    confirmed_stats = mo.production_stats.filter(
        status=SxProductionStat.STATUS_CONFIRMED,
        is_demo=False,
    )
    qty_done = sum(((stat.qty_good or Decimal("0")) for stat in confirmed_stats), Decimal("0"))
    mo.qty_done = qty_done
    if mo.status == SxProductionOrder.STATUS_RELEASED and qty_done > 0:
        mo.status = SxProductionOrder.STATUS_IN_PROGRESS
    if qty_done >= (mo.qty or Decimal("0")) and (mo.qty or Decimal("0")) > 0:
        packing_gate = check_packing_before_done(mo=mo)
        if packing_gate.should_block:
            if mo.status != SxProductionOrder.STATUS_IN_PROGRESS:
                mo.status = SxProductionOrder.STATUS_IN_PROGRESS
        else:
            mo.status = SxProductionOrder.STATUS_DONE
    elif qty_done < (mo.qty or Decimal("0")) and mo.status == SxProductionOrder.STATUS_DONE:
        mo.status = SxProductionOrder.STATUS_IN_PROGRESS if qty_done > 0 else SxProductionOrder.STATUS_RELEASED
    mo.save(update_fields=["qty_done", "status"])
    return mo


@transaction.atomic
def approve_material_issue(
    *,
    request_id: int,
    user,
    attachment=None,
) -> ApprovedIssueResult:
    req = (
        SxMaterialIssueRequest.objects.select_for_update()
        .select_related("production_order")
        .prefetch_related("lines")
        .get(pk=request_id)
    )

    if req.stock_issue_id:
        raise DispatchError("Yêu cầu xuất đã có phiếu xuất kho liên quan.")
    if req.status not in ("draft", "submitted", "approved"):
        raise DispatchError("Yêu cầu xuất không ở trạng thái có thể duyệt.")
    if not req.production_order_id:
        raise DispatchError("Yêu cầu xuất thiếu tham chiếu LSX.")

    mo = req.production_order
    issue = StockIssue(
        number=next_issue_number(),
        issue_date=timezone.localdate(),
        issue_type=ISSUE_TYPE_PRODUCTION,
        production_order=mo.code,
        product_code=mo.product_code,
        issued_by=user,
        created_by=user,
        recipient=user,
        notes=req.notes or "",
    )
    # Attachment: nếu có thì post ngay sau khi tạo lines.
    if attachment is not None:
        issue.attachment = attachment
    issue.save()

    # Tạo StockIssueLine theo từng dòng YCX.
    issue_lines: list[StockIssueLine] = []
    for line in req.lines.all().order_by("id"):
        qty_needed = (line.qty_requested or Decimal("0")).quantize(Decimal("0.001"))
        if qty_needed <= 0:
            continue

        material = _resolve_material_by_code(line.material_code)
        preferred = getattr(line, "preferred_location", None)
        loc_splits = _split_stock_locations(material, qty_needed, preferred=preferred)
        allocations = _allocate_batches(material, qty_needed)
        alloc_i = 0
        alloc_left = allocations[0][1] if allocations else Decimal("0")
        for location, loc_qty in loc_splits:
            need = loc_qty
            while need > 0 and alloc_i < len(allocations):
                batch, _ = allocations[alloc_i]
                take = alloc_left if alloc_left < need else need
                take = take.quantize(Decimal("0.001"))
                if take <= 0:
                    break
                issue_lines.append(
                    StockIssueLine(
                        issue=issue,
                        material=material,
                        quantity=take,
                        location=location,
                        batch=batch,
                        unit_price=Decimal("0"),
                        notes=f"Yêu cầu xuất {req.code} @ {location.code}",
                    )
                )
                need -= take
                alloc_left -= take
                if alloc_left <= 0:
                    alloc_i += 1
                    alloc_left = (
                        allocations[alloc_i][1] if alloc_i < len(allocations) else Decimal("0")
                    )
    if not issue_lines:
        raise DispatchError("Yêu cầu xuất không có dòng NPL với SL cần xuất > 0.")
    StockIssueLine.objects.bulk_create(issue_lines)

    req.stock_issue = issue
    # Nếu chưa upload chứng từ đính kèm thì chỉ tạo phiếu nháp.
    if attachment is None:
        req.status = "approved"
        req.save(update_fields=["stock_issue", "status"])
        return ApprovedIssueResult(request=req, stock_issue=issue)

    # Nếu có attachment thì thực hiện xuất kho thật ngay.
    try:
        issue = post_stock_issue(issue, user)
    except (IssueWorkflowError, BatchWorkflowError) as exc:
        # Nếu post lỗi, để người dùng xử lý lại phiếu xuất kho nháp — vẫn giữ link phiếu.
        req.status = "approved"
        req.save(update_fields=["stock_issue", "status"])
        raise DispatchError(str(exc)) from exc

    # post thành công: cập nhật qty_issued = qty_requested cho tất cả dòng YCX.
    SxMaterialIssueRequestLine.objects.filter(request=req).update(
        qty_issued=dj_models.F("qty_requested"),
    )

    req.status = "done" if issue.status == DOC_STATUS_POSTED else "approved"
    req.save(update_fields=["stock_issue", "status"])
    from kho_npl.services.reservation import consume_reservations_for_ycx

    if req.status == "done":
        consume_reservations_for_ycx(ycx_code=req.code)
    return ApprovedIssueResult(request=req, stock_issue=issue)


@transaction.atomic
def create_production_stat(
    *,
    production_order_id: int,
    stat_date,
    process_name: str = "",
    qty_good: Decimal = Decimal("0"),
    qty_defect: Decimal = Decimal("0"),
    team_label: str = "",
    size_label: str = "",
    sku_code: str = "",
    color_label: str = "",
    color_code: str = "",
    notes: str = "",
    code: str | None = None,
    user=None,
) -> SxProductionStat:
    from san_xuat.services.gates import check_sku_on_stat, enforce_gate
    from san_xuat.services.sku_catalog import SkuError, resolve_sku_fields

    mo = SxProductionOrder.objects.select_for_update().get(pk=production_order_id)
    if mo.status not in (
        SxProductionOrder.STATUS_RELEASED,
        SxProductionOrder.STATUS_IN_PROGRESS,
        SxProductionOrder.STATUS_DONE,
    ):
        raise DispatchError("Chỉ ghi Thống kê sản xuất khi Lệnh sản xuất đã release.")
    if (qty_good or Decimal("0")) <= 0 and (qty_defect or Decimal("0")) <= 0:
        raise DispatchError("Phải nhập ít nhất SL đạt hoặc SL lỗi lớn hơn 0.")

    enforce_gate(
        check_sku_on_stat(
            sku_code=sku_code,
            color_code=color_code or color_label,
            size_label=size_label,
        )
    )

    try:
        resolved = resolve_sku_fields(
            style_code=mo.product_code,
            style_name=mo.product_name or "",
            sku_code=sku_code,
            color_code=color_code,
            color_label=color_label,
            size_label=size_label,
            user=user,
            create_if_missing=True,
        )
    except SkuError as exc:
        raise DispatchError(str(exc)) from exc

    stat = SxProductionStat.objects.create(
        code=_code("stat", SxProductionStat, code=code),
        production_order=mo,
        stat_date=stat_date or timezone.localdate(),
        process_name=(process_name or "").strip(),
        qty_good=qty_good or Decimal("0"),
        qty_defect=qty_defect or Decimal("0"),
        team_label=(team_label or "").strip(),
        sku=resolved.sku,
        size_label=resolved.size_label,
        sku_code=resolved.sku_code,
        color_label=resolved.color_label,
        color_code=resolved.color_code,
        status=SxProductionStat.STATUS_DRAFT,
        notes=notes or "",
    )
    return stat


@transaction.atomic
def confirm_stat(*, stat_id: int) -> SxProductionStat:
    from san_xuat.services.gates import check_issue_before_stat, enforce_gate

    stat = SxProductionStat.objects.select_for_update().select_related("production_order").get(pk=stat_id)
    if stat.status == SxProductionStat.STATUS_CONFIRMED:
        raise DispatchError("Thống kê sản xuất đã được xác nhận trước đó.")
    warn = enforce_gate(check_issue_before_stat(mo=stat.production_order))
    # Cảnh báo (warn) không chặn — caller/view có thể hiển thị thêm; block đã raise ở enforce_gate.
    _ = warn
    stat.status = SxProductionStat.STATUS_CONFIRMED
    stat.save(update_fields=["status"])
    _recompute_mo_progress(stat.production_order)
    if (stat.process_name or "").strip() and (stat.qty_good or Decimal("0")) > 0:
        _adjust_wip_balance(
            production_order=stat.production_order,
            process_name=stat.process_name,
            delta=stat.qty_good,
            allow_negative=False,
        )

    from san_xuat.services.qc import process_stat_qc_link

    process_stat_qc_link(stat_id=stat.pk)
    return stat


@transaction.atomic
def create_fg_receipt_from_mo(
    *,
    production_order_id: int,
    stat_id: int | None = None,
    qty: Decimal | None = None,
    code: str | None = None,
    notes: str = "",
) -> SxFgReceiptRequest:
    mo = SxProductionOrder.objects.select_for_update().get(pk=production_order_id)
    if mo.status not in (
        SxProductionOrder.STATUS_IN_PROGRESS,
        SxProductionOrder.STATUS_DONE,
    ):
        raise DispatchError("Chỉ tạo Yêu cầu nhập thành phẩm khi Lệnh sản xuất đang SX hoặc đã hoàn thành.")

    stat = None
    if stat_id:
        stat = SxProductionStat.objects.filter(pk=stat_id, production_order=mo).first()
        if not stat:
            raise DispatchError("Thống kê sản xuất không thuộc Lệnh sản xuất này.")
        if stat.status != SxProductionStat.STATUS_CONFIRMED:
            raise DispatchError("Thống kê sản xuất phải đã xác nhận trước khi lập YCNTP.")

    receipt_qty = qty
    if receipt_qty is None:
        if stat and (stat.qty_good or Decimal("0")) > 0:
            receipt_qty = stat.qty_good
        else:
            receipt_qty = mo.qty_done or Decimal("0")
    if (receipt_qty or Decimal("0")) <= 0:
        raise DispatchError("SL nhập TP phải > 0 — cần Thống kê sản xuất đã xác nhận hoặc Lệnh sản xuất có qty_done.")

    from san_xuat.services.gates import (
        check_open_qc_alert_before_fg,
        check_qc_pass_before_fg,
        check_stat_before_fg,
        enforce_gate,
    )

    enforce_gate(check_stat_before_fg(mo=mo))
    enforce_gate(check_open_qc_alert_before_fg(mo=mo))
    enforce_gate(check_qc_pass_before_fg(mo=mo))

    from san_xuat.hub_models import SxFgReceiptLine

    req = SxFgReceiptRequest.objects.create(
        code=_code("fg", SxFgReceiptRequest, code=code),
        production_order=mo,
        production_stat=stat,
        request_date=timezone.localdate(),
        qty=receipt_qty,
        status=SxFgReceiptRequest.STATUS_DRAFT,
        notes=notes or "",
        is_demo=False,
    )
    # Khi YCNTP lấy từ TKSX có SKU → tạo 1 dòng biến thể (Style–Màu–Size).
    if stat and (stat.sku_id or (stat.sku_code or "").strip()):
        SxFgReceiptLine.objects.create(
            receipt=req,
            sku_id=stat.sku_id,
            sku_code=(stat.sku_code or "").strip(),
            size_label=(stat.size_label or "").strip(),
            color_label=(stat.color_label or "").strip(),
            color_code=(stat.color_code or "").strip(),
            qty=receipt_qty,
        )
    return req


@transaction.atomic
def submit_fg_receipt(*, request_id: int) -> SxFgReceiptRequest:
    from san_xuat.services.sx_settings import sx_bool

    req = SxFgReceiptRequest.objects.select_for_update().get(pk=request_id)
    if req.status != SxFgReceiptRequest.STATUS_DRAFT:
        raise DispatchError("Chỉ gửi Yêu cầu nhập thành phẩm ở trạng thái nháp.")
    require_kv = sx_bool("require_kv_link_for_fg_done", True)
    if require_kv:
        req.status = SxFgReceiptRequest.STATUS_SUBMITTED
    else:
        # Không bắt buộc KV → gửi xong coi như hoàn tất
        req.status = SxFgReceiptRequest.STATUS_DONE
    req.save(update_fields=["status"])
    return req


@transaction.atomic
def link_kv_purchase(
    *,
    request_id: int,
    kv_purchase_kiotviet_id: int | None = None,
    kv_purchase_code: str = "",
) -> SxFgReceiptRequest:
    from kiotviet.models import KvPurchaseOrder
    from kiotviet.sync_service import current_retailer

    req = SxFgReceiptRequest.objects.select_for_update().get(pk=request_id)
    if req.status == SxFgReceiptRequest.STATUS_CANCELLED:
        raise DispatchError("Yêu cầu nhập thành phẩm đã hủy.")

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
        raise DispatchError("Không tìm thấy phiếu nhập KV trong dữ liệu đã sync.")

    req.kv_purchase_kiotviet_id = purchase.kiotviet_id
    req.kv_purchase_code = purchase.code or ""
    if req.status in (SxFgReceiptRequest.STATUS_DRAFT, SxFgReceiptRequest.STATUS_SUBMITTED):
        req.status = SxFgReceiptRequest.STATUS_DONE
    req.save(update_fields=["kv_purchase_kiotviet_id", "kv_purchase_code", "status"])
    return req


@transaction.atomic
def create_mos_from_detail_plan(
    *,
    detail_plan_id: int,
    team_label: str = "",
    notes: str = "",
) -> list[SxProductionOrder]:
    plan = (
        SxDetailPlan.objects.select_for_update()
        .prefetch_related("lines")
        .get(pk=detail_plan_id)
    )
    if plan.status != SxOverallPlan.STATUS_CONFIRMED:
        raise DispatchError("KHCT phải đã xác nhận trước khi sinh LSX.")

    created: list[SxProductionOrder] = []
    skipped = 0
    for line in plan.lines.filter(qty__gt=0).order_by("plan_date", "product_code"):
        exists = SxProductionOrder.objects.filter(
            is_demo=False,
            detail_plan=plan,
            product_code__iexact=line.product_code,
            planned_start=line.plan_date,
        ).exists()
        if exists:
            skipped += 1
            continue
        mo = create_mo_from_bom(
            product_code=line.product_code,
            qty=line.qty,
            order_date=line.plan_date,
            due_date=line.plan_date,
            planned_start=line.plan_date,
            planned_end=line.plan_date,
            team_label=team_label,
            notes=notes or f"Từ KHCT {plan.code}",
            detail_plan_id=plan.pk,
        )
        if line.product_name:
            mo.product_name = line.product_name
            mo.save(update_fields=["product_name"])
        created.append(mo)

    if not created and skipped == 0:
        raise DispatchError("KHCT không có dòng SL > 0 để tạo LSX.")
    return created


def _adjust_wip_balance(
    *,
    production_order: SxProductionOrder,
    process_name: str,
    delta: Decimal,
    allow_negative: bool = False,
) -> SxWipBalance:
    name = (process_name or "").strip()
    if not name:
        raise DispatchError("Thiếu tên công đoạn khi cập nhật tồn BTP.")
    bal, _ = SxWipBalance.objects.select_for_update().get_or_create(
        production_order=production_order,
        process_name=name,
        defaults={"qty": Decimal("0"), "is_demo": False},
    )
    new_qty = (bal.qty or Decimal("0")) + Decimal(str(delta))
    if not allow_negative and new_qty < 0:
        raise DispatchError(
            f"Tồn BTP tại «{name}» không đủ (có {bal.qty}, trừ {abs(delta)})."
        )
    bal.qty = new_qty.quantize(Decimal("0.01"))
    bal.save(update_fields=["qty", "updated_at"])
    return bal


def list_wip_balances(*, production_order_id: int | None = None):
    qs = SxWipBalance.objects.filter(is_demo=False).select_related("production_order")
    if production_order_id:
        qs = qs.filter(production_order_id=production_order_id)
    return qs.order_by("production_order__code", "process_name")


@transaction.atomic
def create_wip_handover(
    *,
    production_order_id: int,
    from_process: str,
    to_process: str,
    qty: Decimal,
    handover_date=None,
    code: str | None = None,
    notes: str = "",
) -> SxWipHandover:
    mo = SxProductionOrder.objects.select_for_update().get(pk=production_order_id)
    if mo.status not in (
        SxProductionOrder.STATUS_RELEASED,
        SxProductionOrder.STATUS_IN_PROGRESS,
        SxProductionOrder.STATUS_DONE,
    ):
        raise DispatchError("Chỉ bàn giao BTP khi Lệnh sản xuất đã release.")
    if qty is None or qty <= 0:
        raise DispatchError("SL bàn giao phải > 0.")
    if not (from_process or "").strip() or not (to_process or "").strip():
        raise DispatchError("Phải nhập công đoạn gửi và nhận.")

    handover = SxWipHandover.objects.create(
        code=_code("wip_ho", SxWipHandover, code=code),
        production_order=mo,
        from_process=(from_process or "").strip(),
        to_process=(to_process or "").strip(),
        qty=qty.quantize(Decimal("0.01")),
        handover_date=handover_date or timezone.localdate(),
        status=SxWipHandover.STATUS_PENDING,
        notes=notes or "",
        is_demo=False,
    )
    return handover


@transaction.atomic
def confirm_wip_handover(*, handover_id: int) -> SxWipHandover:
    handover = (
        SxWipHandover.objects.select_for_update()
        .select_related("production_order")
        .get(pk=handover_id)
    )
    if handover.status != SxWipHandover.STATUS_PENDING:
        raise DispatchError("Chỉ xác nhận bàn giao đang chờ.")
    qty = handover.qty or Decimal("0")
    try:
        _adjust_wip_balance(
            production_order=handover.production_order,
            process_name=handover.from_process,
            delta=-qty,
            allow_negative=False,
        )
    except DispatchError:
        # Lần đầu chưa có tồn từ TKSX: seed rồi trừ để ghi nhận chuyển CĐ
        _adjust_wip_balance(
            production_order=handover.production_order,
            process_name=handover.from_process,
            delta=qty,
            allow_negative=False,
        )
        _adjust_wip_balance(
            production_order=handover.production_order,
            process_name=handover.from_process,
            delta=-qty,
            allow_negative=False,
        )
    _adjust_wip_balance(
        production_order=handover.production_order,
        process_name=handover.to_process,
        delta=qty,
        allow_negative=False,
    )
    handover.status = SxWipHandover.STATUS_DONE
    handover.save(update_fields=["status"])
    return handover


@transaction.atomic
def reject_wip_handover(*, handover_id: int, notes: str = "") -> SxWipHandover:
    handover = SxWipHandover.objects.select_for_update().get(pk=handover_id)
    if handover.status != SxWipHandover.STATUS_PENDING:
        raise DispatchError("Chỉ từ chối bàn giao đang chờ.")
    handover.status = SxWipHandover.STATUS_REJECTED
    if notes:
        handover.notes = notes
        handover.save(update_fields=["status", "notes"])
    else:
        handover.save(update_fields=["status"])
    return handover


@transaction.atomic
def create_wip_return(
    *,
    production_order_id: int,
    qty: Decimal,
    reason: str = "",
    handover_id: int | None = None,
    from_process: str = "",
    to_process: str = "",
    return_date=None,
    code: str | None = None,
    notes: str = "",
) -> SxWipReturn:
    """Trả BTP về công đoạn trước (sửa lỗi) — gắn bàn giao đã xác nhận nếu có."""
    mo = SxProductionOrder.objects.select_for_update().get(pk=production_order_id)
    if mo.status not in (
        SxProductionOrder.STATUS_RELEASED,
        SxProductionOrder.STATUS_IN_PROGRESS,
        SxProductionOrder.STATUS_DONE,
    ):
        raise DispatchError("Chỉ trả BTP khi Lệnh sản xuất đã release.")
    if qty is None or qty <= 0:
        raise DispatchError("SL trả phải > 0.")

    handover = None
    if handover_id:
        handover = SxWipHandover.objects.select_for_update().get(pk=handover_id)
        if handover.production_order_id != mo.pk:
            raise DispatchError("Bàn giao không thuộc Lệnh sản xuất này.")
        if handover.status != SxWipHandover.STATUS_DONE:
            raise DispatchError("Chỉ trả từ bàn giao đã xác nhận.")
        returned = sum(
            (
                r.qty
                for r in handover.returns.filter(
                    status=SxWipReturn.STATUS_CONFIRMED,
                    is_demo=False,
                )
            ),
            Decimal("0"),
        )
        remaining = (handover.qty or Decimal("0")) - returned
        if qty > remaining:
            raise DispatchError(f"SL trả vượt SL còn lại của bàn giao ({remaining}).")
        from_process = from_process or handover.to_process
        to_process = to_process or handover.from_process

    if not (from_process or "").strip() or not (to_process or "").strip():
        raise DispatchError("Phải nhập công đoạn nguồn và đích trả.")

    return SxWipReturn.objects.create(
        code=_code("wip_ret", SxWipReturn, code=code),
        handover=handover,
        production_order=mo,
        from_process=(from_process or "").strip(),
        to_process=(to_process or "").strip(),
        qty=qty.quantize(Decimal("0.01")),
        return_date=return_date or timezone.localdate(),
        reason=(reason or "").strip(),
        status=SxWipReturn.STATUS_DRAFT,
        notes=notes or "",
        is_demo=False,
    )


@transaction.atomic
def confirm_wip_return(*, return_id: int) -> SxWipReturn:
    item = SxWipReturn.objects.select_for_update().get(pk=return_id)
    if item.status != SxWipReturn.STATUS_DRAFT:
        raise DispatchError("Chỉ xác nhận phiếu trả ở trạng thái nháp.")
    if item.handover_id:
        handover = SxWipHandover.objects.select_for_update().get(pk=item.handover_id)
        returned = sum(
            (
                r.qty
                for r in handover.returns.filter(
                    status=SxWipReturn.STATUS_CONFIRMED,
                    is_demo=False,
                ).exclude(pk=item.pk)
            ),
            Decimal("0"),
        )
        remaining = (handover.qty or Decimal("0")) - returned
        if item.qty > remaining:
            raise DispatchError(f"SL trả vượt SL còn lại của bàn giao ({remaining}).")
    qty = item.qty or Decimal("0")
    _adjust_wip_balance(
        production_order=item.production_order,
        process_name=item.from_process,
        delta=-qty,
        allow_negative=False,
    )
    _adjust_wip_balance(
        production_order=item.production_order,
        process_name=item.to_process,
        delta=qty,
        allow_negative=False,
    )
    item.status = SxWipReturn.STATUS_CONFIRMED
    item.confirmed_at = timezone.now()
    item.save(update_fields=["status", "confirmed_at"])
    return item


@transaction.atomic
def cancel_wip_return(*, return_id: int) -> SxWipReturn:
    item = SxWipReturn.objects.select_for_update().get(pk=return_id)
    if item.status != SxWipReturn.STATUS_DRAFT:
        raise DispatchError("Chỉ hủy phiếu trả nháp.")
    item.status = SxWipReturn.STATUS_CANCELLED
    item.save(update_fields=["status"])
    return item


@transaction.atomic
def update_mo_schedule(
    *,
    production_order_id: int,
    planned_start=None,
    planned_end=None,
    team_label: str | None = None,
) -> SxProductionOrder:
    """Cập nhật lịch / tổ trên Lệnh sản xuất (lịch SX editable)."""
    mo = SxProductionOrder.objects.select_for_update().get(pk=production_order_id)
    if mo.status in (SxProductionOrder.STATUS_CANCELLED,):
        raise DispatchError("Không sửa lịch Lệnh sản xuất đã hủy.")
    fields = []
    if planned_start is not None:
        mo.planned_start = planned_start or None
        fields.append("planned_start")
    if planned_end is not None:
        mo.planned_end = planned_end or None
        fields.append("planned_end")
    if team_label is not None:
        mo.team_label = (team_label or "").strip()
        fields.append("team_label")
    if mo.planned_start and mo.planned_end and mo.planned_start > mo.planned_end:
        raise DispatchError("Ngày bắt đầu không được sau ngày kết thúc.")
    if fields:
        mo.save(update_fields=fields)
    return mo


@transaction.atomic
def explode_disassembly_from_bom(*, order_id: int) -> SxDisassemblyOrder:
    """Đổ dòng thu hồi NVL từ BOM active × SL tháo (BOM tháo)."""
    from san_xuat.hub_models import SxDisassemblyOrderLine
    from san_xuat.models import ProductTechDoc
    from san_xuat.services.bom import get_active_bom

    order = SxDisassemblyOrder.objects.select_for_update().get(pk=order_id)
    if order.status != SxDisassemblyOrder.STATUS_DRAFT:
        raise DispatchError("Chỉ explode BOM khi LTD nháp.")
    doc = ProductTechDoc.objects.filter(product_code__iexact=order.product_code, is_active=True).first()
    if not doc:
        raise DispatchError(f"Không có hồ sơ SX cho {order.product_code}.")
    bom = get_active_bom(doc)
    if not bom:
        raise DispatchError(f"Không có BOM active cho {order.product_code}.")
    order.lines.all().delete()
    create_lines = []
    for bl in bom.lines.select_related("material").all():
        qty = (bl.qty_with_scrap * (order.qty or Decimal("0"))).quantize(Decimal("0.0001"))
        if qty <= 0:
            continue
        create_lines.append(
            SxDisassemblyOrderLine(
                order=order,
                material_code=bl.material.code,
                material_name=bl.material.name,
                qty=qty,
                notes=f"BOM {bom.version_label}" + (f" size {bl.size_code}" if bl.size_code else ""),
            )
        )
    if not create_lines:
        raise DispatchError("BOM không có dòng nguyên phụ liệu để thu hồi.")
    SxDisassemblyOrderLine.objects.bulk_create(create_lines)
    return order


def _default_stock_location() -> WarehouseLocation:
    loc = WarehouseLocation.objects.filter(code="MAIN", is_active=True).first()
    if not loc:
        loc = WarehouseLocation.objects.filter(is_active=True).order_by("code").first()
    if not loc:
        raise DispatchError("Chưa có vị trí kho NPL.")
    return loc


def _surplus_batch_for_material(material: Material):
    from kho_npl.models import MaterialBatch

    today = timezone.localdate()
    batch_code = f"THUA-{today.strftime('%Y%m%d')}"
    batch, _ = MaterialBatch.objects.get_or_create(
        material=material,
        code=batch_code,
        defaults={
            "unit_price": Decimal("0"),
            "quantity": Decimal("0"),
            "received_date": today,
            "is_active": True,
        },
    )
    return batch


@transaction.atomic
def create_disassembly_order(
    *,
    product_code: str,
    qty: Decimal,
    order_date=None,
    product_name: str = "",
    production_order_id: int | None = None,
    code: str | None = None,
    notes: str = "",
    lines: list[dict] | None = None,
) -> SxDisassemblyOrder:
    from san_xuat.hub_models import SxDisassemblyOrderLine

    product_code = (product_code or "").strip()
    if not product_code:
        raise DispatchError("Thiếu mã SP tháo dỡ.")
    if qty is None or qty <= 0:
        raise DispatchError("SL tháo dỡ phải > 0.")

    mo = None
    if production_order_id:
        mo = SxProductionOrder.objects.select_for_update().get(pk=production_order_id)
        if not product_name:
            product_name = mo.product_name

    order = SxDisassemblyOrder.objects.create(
        code=_code("disassembly", SxDisassemblyOrder, code=code),
        production_order=mo,
        product_code=product_code,
        product_name=(product_name or "").strip(),
        qty=qty.quantize(Decimal("0.01")),
        order_date=order_date or timezone.localdate(),
        status=SxDisassemblyOrder.STATUS_DRAFT,
        notes=notes or "",
        is_demo=False,
    )

    if lines:
        create_lines: list[SxDisassemblyOrderLine] = []
        for raw in lines:
            mat_code = (raw.get("material_code") or "").strip()
            mat_qty = Decimal(str(raw.get("qty") or 0)).quantize(Decimal("0.0001"))
            if not mat_code or mat_qty <= 0:
                continue
            mat_name = (raw.get("material_name") or "").strip()
            if not mat_name:
                try:
                    mat_name = _resolve_material_by_code(mat_code).name
                except DispatchError:
                    mat_name = ""
            create_lines.append(
                SxDisassemblyOrderLine(
                    order=order,
                    material_code=mat_code,
                    material_name=mat_name,
                    qty=mat_qty,
                    notes=(raw.get("notes") or "").strip(),
                )
            )
        if create_lines:
            SxDisassemblyOrderLine.objects.bulk_create(create_lines)
    return order


@transaction.atomic
def set_disassembly_lines(*, order_id: int, lines: list[dict]) -> SxDisassemblyOrder:
    from san_xuat.hub_models import SxDisassemblyOrderLine

    order = SxDisassemblyOrder.objects.select_for_update().get(pk=order_id)
    if order.status != SxDisassemblyOrder.STATUS_DRAFT:
        raise DispatchError("Chỉ sửa dòng thu hồi khi LTD ở trạng thái nháp.")
    order.lines.all().delete()
    create_lines: list[SxDisassemblyOrderLine] = []
    for raw in lines:
        mat_code = (raw.get("material_code") or "").strip()
        mat_qty = Decimal(str(raw.get("qty") or 0)).quantize(Decimal("0.0001"))
        if not mat_code or mat_qty <= 0:
            continue
        mat_name = (raw.get("material_name") or "").strip()
        if not mat_name:
            try:
                mat_name = _resolve_material_by_code(mat_code).name
            except DispatchError:
                mat_name = ""
        create_lines.append(
            SxDisassemblyOrderLine(
                order=order,
                material_code=mat_code,
                material_name=mat_name,
                qty=mat_qty,
                notes=(raw.get("notes") or "").strip(),
            )
        )
    if create_lines:
        SxDisassemblyOrderLine.objects.bulk_create(create_lines)
    return order


@transaction.atomic
def confirm_disassembly_order(*, order_id: int, create_surplus: bool = True) -> SxDisassemblyOrder:
    """Xác nhận LTD; tùy chọn sinh phiếu NPL thừa nháp từ dòng thu hồi."""
    order = (
        SxDisassemblyOrder.objects.select_for_update()
        .prefetch_related("lines")
        .get(pk=order_id)
    )
    if order.status != SxDisassemblyOrder.STATUS_DRAFT:
        raise DispatchError("Chỉ xác nhận LTD ở trạng thái nháp.")
    if not order.lines.exists():
        raise DispatchError("LTD phải có ít nhất một dòng nguyên phụ liệu thu hồi.")

    if create_surplus:
        for line in order.lines.all():
            SxNplSurplus.objects.create(
                code=_code("npl_surplus", SxNplSurplus),
                production_order=order.production_order,
                disassembly_order=order,
                material_code=line.material_code,
                material_name=line.material_name,
                qty=line.qty,
                recorded_at=timezone.localdate(),
                status=SxNplSurplus.STATUS_DRAFT,
                notes=f"Từ LTD {order.code}",
                is_demo=False,
            )

    order.status = SxDisassemblyOrder.STATUS_CONFIRMED
    order.save(update_fields=["status"])
    return order


@transaction.atomic
def create_npl_surplus(
    *,
    material_code: str,
    qty: Decimal,
    recorded_at=None,
    material_name: str = "",
    production_order_id: int | None = None,
    disassembly_order_id: int | None = None,
    code: str | None = None,
    notes: str = "",
) -> SxNplSurplus:
    material_code = (material_code or "").strip()
    if not material_code:
        raise DispatchError("Thiếu mã NPL thừa.")
    if qty is None or qty <= 0:
        raise DispatchError("SL thừa phải > 0.")

    material = _resolve_material_by_code(material_code)
    mo = None
    if production_order_id:
        mo = SxProductionOrder.objects.get(pk=production_order_id)
    ltd = None
    if disassembly_order_id:
        ltd = SxDisassemblyOrder.objects.get(pk=disassembly_order_id)

    return SxNplSurplus.objects.create(
        code=_code("npl_surplus", SxNplSurplus, code=code),
        production_order=mo,
        disassembly_order=ltd,
        material_code=material.code,
        material_name=(material_name or "").strip() or material.name,
        qty=qty.quantize(Decimal("0.0001")),
        recorded_at=recorded_at or timezone.localdate(),
        status=SxNplSurplus.STATUS_DRAFT,
        notes=notes or "",
        is_demo=False,
    )


@transaction.atomic
def confirm_npl_surplus(*, surplus_id: int, user) -> SxNplSurplus:
    """Duyệt NPL thừa → tạo + duyệt phiếu điều chỉnh kho (+qty)."""
    from kho_npl.choices import ADJUST_STATUS_PENDING
    from kho_npl.models import StockAdjustment, StockAdjustmentLine, StockBalance
    from kho_npl.services.adjustments import AdjustmentWorkflowError, approve_stock_adjustment
    from kho_npl.services.doc_numbers import next_adjustment_number

    surplus = SxNplSurplus.objects.select_for_update().get(pk=surplus_id)
    if surplus.status != SxNplSurplus.STATUS_DRAFT:
        raise DispatchError("Chỉ xác nhận NPL thừa ở trạng thái nháp.")
    if surplus.stock_adjustment_id:
        raise DispatchError("NPL thừa đã có phiếu điều chỉnh kho.")

    material = _resolve_material_by_code(surplus.material_code)
    location = _default_stock_location()
    system_qty = Decimal("0")
    bal = StockBalance.objects.filter(material=material, location=location).first()
    if bal:
        system_qty = bal.quantity or Decimal("0")
    actual_qty = (system_qty + (surplus.qty or Decimal("0"))).quantize(Decimal("0.001"))
    batch = _surplus_batch_for_material(material)

    adj = StockAdjustment.objects.create(
        number=next_adjustment_number(),
        adjust_date=surplus.recorded_at or timezone.localdate(),
        reason=f"NPL thừa {surplus.code}" + (f" — {surplus.notes}" if surplus.notes else ""),
        proposed_by=user,
        status=ADJUST_STATUS_PENDING,
    )
    StockAdjustmentLine.objects.create(
        adjustment=adj,
        material=material,
        location=location,
        system_qty=system_qty.quantize(Decimal("0.001")),
        actual_qty=actual_qty,
        batch=batch,
        notes=f"NPLT {surplus.code}",
    )
    try:
        approve_stock_adjustment(adj, user)
    except AdjustmentWorkflowError as exc:
        raise DispatchError(str(exc)) from exc

    surplus.stock_adjustment = adj
    surplus.status = SxNplSurplus.STATUS_CONFIRMED
    surplus.save(update_fields=["stock_adjustment", "status"])
    return surplus

