"""Giai đoạn 3 — giao việc, truy xuất, năng lực, đóng gói, thuê GC (làm dày)."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from decimal import Decimal
from io import StringIO

from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.http import HttpResponse
from django.utils import timezone

from san_xuat.hub_models import (
    SxDowntimeEvent,
    SxFgReceiptRequest,
    SxMaterialIssueRequest,
    SxPackingLine,
    SxPackingRecord,
    SxProductionOrder,
    SxProductionStat,
    SxQcAlert,
    SxQcRequest,
    SxSubcontractMaterialLine,
    SxSubcontractOrder,
    SxWorkAssignment,
    SxWorkCenter,
)


class Phase3Error(Exception):
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


def _user_display(user) -> str:
    if not user:
        return ""
    full = (user.get_full_name() or "").strip()
    return full or user.username


# --- Giao việc ---


@transaction.atomic
def create_work_assignment(
    *,
    production_order_id: int,
    title: str,
    process_name: str = "",
    assignee_label: str = "",
    due_date=None,
    code: str | None = None,
    notes: str = "",
    work_center_id: int | None = None,
    assignee_id: int | None = None,
    create_portal_task: bool = False,
    assigner=None,
) -> SxWorkAssignment:
    from django.contrib.auth import get_user_model
    from tasks.models import WorkTask

    mo = SxProductionOrder.objects.select_for_update().get(pk=production_order_id)
    title = (title or "").strip()
    if not title:
        raise Phase3Error("Thiếu tiêu đề giao việc.")

    center = None
    if work_center_id:
        center = SxWorkCenter.objects.get(pk=work_center_id)

    assignee = None
    User = get_user_model()
    if assignee_id:
        assignee = User.objects.get(pk=assignee_id)
        if not assignee_label:
            assignee_label = _user_display(assignee)

    if center and not assignee_label:
        assignee_label = center.name

    item = SxWorkAssignment.objects.create(
        code=(code or "").strip() or _next_code("GV", SxWorkAssignment),
        production_order=mo,
        work_center=center,
        assignee=assignee,
        process_name=(process_name or "").strip(),
        title=title,
        assignee_label=(assignee_label or "").strip(),
        due_date=due_date,
        status=SxWorkAssignment.STATUS_OPEN,
        notes=notes or "",
        is_demo=False,
    )

    if create_portal_task:
        if not assigner:
            raise Phase3Error("Thiếu người giao để tạo công việc portal.")
        if not assignee:
            raise Phase3Error("Chọn người nhận portal để tạo WorkTask.")
        task = WorkTask.objects.create(
            title=title,
            description=(
                f"Lệnh sản xuất {mo.code} · {mo.product_code} — {mo.product_name}\n"
                f"Công đoạn: {(process_name or '').strip() or '—'}\n"
                f"{notes or ''}"
            ).strip(),
            task_type=WorkTask.TYPE_PRODUCTION,
            production_order=mo,
            process_name=(process_name or "").strip(),
            priority=WorkTask.PRIORITY_NORMAL,
            assigner=assigner,
            assignee=assignee,
            due_date=due_date,
            skip_completion_review=True,
        )
        item.work_task = task
        item.save(update_fields=["work_task"])

    return item


@transaction.atomic
def complete_work_assignment(*, assignment_id: int) -> SxWorkAssignment:
    from tasks.models import WorkTask

    item = (
        SxWorkAssignment.objects.select_for_update()
        .select_related("work_task")
        .get(pk=assignment_id)
    )
    if item.status != SxWorkAssignment.STATUS_OPEN:
        raise Phase3Error("Chỉ hoàn thành việc đang giao.")
    item.status = SxWorkAssignment.STATUS_DONE
    item.completed_at = timezone.now()
    item.save(update_fields=["status", "completed_at"])

    task = item.work_task
    if task and task.status not in {
        WorkTask.STATUS_COMPLETED,
        WorkTask.STATUS_CANCELLED,
    }:
        task.status = WorkTask.STATUS_COMPLETED
        task.save(update_fields=["status", "updated_at"])
    return item


# --- Năng lực ---


@transaction.atomic
def upsert_work_center(
    *,
    code: str,
    name: str,
    capacity_per_day: Decimal,
    uom_label: str = "SP",
    team_label: str = "",
    is_active: bool = True,
    notes: str = "",
    center_id: int | None = None,
    user=None,
) -> SxWorkCenter:
    code = (code or "").strip().upper()
    name = (name or "").strip()
    if not code or not name:
        raise Phase3Error("Mã và tên tổ/chuyền là bắt buộc.")
    if capacity_per_day is None or capacity_per_day < 0:
        raise Phase3Error("Năng lực/ngày không hợp lệ.")
    capacity_per_day = Decimal(str(capacity_per_day)).quantize(Decimal("0.01"))
    team_label = (team_label or "").strip() or name
    if center_id:
        center = SxWorkCenter.objects.select_for_update().get(pk=center_id)
        if SxWorkCenter.objects.filter(code__iexact=code).exclude(pk=center.pk).exists():
            raise Phase3Error(f"Mã tổ/chuyền đã tồn tại: {code}")
        center.code = code
        center.name = name
        center.capacity_per_day = capacity_per_day
        center.uom_label = (uom_label or "SP").strip() or "SP"
        center.team_label = team_label
        center.is_active = is_active
        center.notes = notes or ""
        center.save()
        return center
    if SxWorkCenter.objects.filter(code__iexact=code).exists():
        raise Phase3Error(f"Mã tổ/chuyền đã tồn tại: {code}")
    return SxWorkCenter.objects.create(
        code=code,
        name=name,
        capacity_per_day=capacity_per_day,
        uom_label=(uom_label or "SP").strip() or "SP",
        team_label=team_label,
        is_active=is_active,
        notes=notes or "",
        is_demo=False,
        user=user,
    )


@dataclass
class CapacityLoadRow:
    center: SxWorkCenter
    days: int
    capacity_period: Decimal
    assigned_open: Decimal
    output_period: Decimal
    load_pct: float
    utilization_pct: float


def build_capacity_load(*, date_from, date_to) -> list[CapacityLoadRow]:
    days = max((date_to - date_from).days + 1, 1)
    centers = list(SxWorkCenter.objects.filter(is_demo=False, is_active=True).order_by("code"))
    rows: list[CapacityLoadRow] = []
    for center in centers:
        capacity = (center.capacity_per_day or Decimal("0")) * days
        assigned = (
            SxWorkAssignment.objects.filter(
                is_demo=False,
                work_center=center,
                status=SxWorkAssignment.STATUS_OPEN,
            )
            .aggregate(q=Coalesce(Sum("production_order__qty"), Decimal("0")))
        )
        # Sum of open MO qty linked via assignments (rough load signal)
        assigned_qty = Decimal(str(assigned["q"] or 0))
        # Prefer remaining work on open assignments' MOs
        open_mo_ids = (
            SxWorkAssignment.objects.filter(
                is_demo=False,
                work_center=center,
                status=SxWorkAssignment.STATUS_OPEN,
            )
            .values_list("production_order_id", flat=True)
            .distinct()
        )
        remaining = Decimal("0")
        for mo in SxProductionOrder.objects.filter(pk__in=open_mo_ids):
            rem = (mo.qty or Decimal("0")) - (mo.qty_done or Decimal("0"))
            if rem > 0:
                remaining += rem
        load_base = remaining if remaining > 0 else assigned_qty

        team = (center.team_label or center.name or "").strip()
        out_agg = SxProductionStat.objects.filter(
            is_demo=False,
            status=SxProductionStat.STATUS_CONFIRMED,
            stat_date__gte=date_from,
            stat_date__lte=date_to,
            team_label__iexact=team,
        ).aggregate(q=Coalesce(Sum("qty_good"), Decimal("0")))
        output = Decimal(str(out_agg["q"] or 0))

        cap_f = float(capacity) if capacity else 0.0
        load_pct = (float(load_base) / cap_f * 100.0) if cap_f else 0.0
        util_pct = (float(output) / cap_f * 100.0) if cap_f else 0.0
        rows.append(
            CapacityLoadRow(
                center=center,
                days=days,
                capacity_period=capacity,
                assigned_open=load_base,
                output_period=output,
                load_pct=round(load_pct, 1),
                utilization_pct=round(util_pct, 1),
            )
        )
    return rows


# --- Đóng gói ---


@transaction.atomic
def create_packing_record(
    *,
    production_order_id: int,
    qty: Decimal | None = None,
    pack_date=None,
    carton_count: int = 0,
    lot_code: str = "",
    fg_receipt_id: int | None = None,
    code: str | None = None,
    notes: str = "",
    lines: list[dict] | None = None,
) -> SxPackingRecord:
    mo = SxProductionOrder.objects.select_for_update().get(pk=production_order_id)
    line_rows = [
        row for row in (lines or [])
        if row.get("qty") is not None and Decimal(str(row["qty"])) > 0
    ]
    if line_rows:
        total_qty = sum(Decimal(str(r["qty"])) for r in line_rows)
        total_cartons = sum(int(r.get("carton_count") or 0) for r in line_rows)
    else:
        if qty is None or qty <= 0:
            raise Phase3Error("SL đóng gói phải > 0 (hoặc nhập dòng size/SKU).")
        total_qty = Decimal(str(qty)).quantize(Decimal("0.01"))
        total_cartons = max(int(carton_count or 0), 0)

    fg = None
    if fg_receipt_id:
        fg = SxFgReceiptRequest.objects.get(pk=fg_receipt_id)
        if fg.production_order_id and fg.production_order_id != mo.pk:
            raise Phase3Error("Yêu cầu nhập thành phẩm không thuộc Lệnh sản xuất đã chọn.")
    elif not fg_receipt_id:
        # Auto-pick latest FG for MO if available
        fg = (
            SxFgReceiptRequest.objects.filter(is_demo=False, production_order=mo)
            .order_by("-request_date", "-pk")
            .first()
        )

    item = SxPackingRecord.objects.create(
        code=(code or "").strip() or _next_code("DG", SxPackingRecord),
        production_order=mo,
        fg_receipt=fg,
        pack_date=pack_date or timezone.localdate(),
        qty=total_qty.quantize(Decimal("0.01")),
        carton_count=total_cartons,
        lot_code=(lot_code or "").strip(),
        status=SxPackingRecord.STATUS_DRAFT,
        notes=notes or "",
        is_demo=False,
    )
    for row in line_rows:
        SxPackingLine.objects.create(
            packing=item,
            sku_code=(row.get("sku_code") or "").strip(),
            size_label=(row.get("size_label") or "").strip(),
            color_label=(row.get("color_label") or "").strip(),
            qty=Decimal(str(row["qty"])).quantize(Decimal("0.01")),
            carton_count=max(int(row.get("carton_count") or 0), 0),
        )
    return item


@transaction.atomic
def confirm_packing_record(*, packing_id: int) -> SxPackingRecord:
    item = SxPackingRecord.objects.select_for_update().prefetch_related("lines").get(pk=packing_id)
    if item.status != SxPackingRecord.STATUS_DRAFT:
        raise Phase3Error("Chỉ xác nhận phiếu đóng gói nháp.")
    if not item.lot_code:
        item.lot_code = f"LO-{item.code}"
    item.status = SxPackingRecord.STATUS_CONFIRMED
    item.confirmed_at = timezone.now()
    item.save(update_fields=["status", "lot_code", "confirmed_at"])
    return item


# --- Thuê gia công ---


@transaction.atomic
def create_subcontract_order(
    *,
    vendor_name: str,
    product_code: str,
    qty: Decimal,
    order_date=None,
    product_name: str = "",
    process_name: str = "",
    production_order_id: int | None = None,
    due_date=None,
    code: str | None = None,
    notes: str = "",
    out_lines: list[dict] | None = None,
) -> SxSubcontractOrder:
    vendor_name = (vendor_name or "").strip()
    product_code = (product_code or "").strip()
    if not vendor_name:
        raise Phase3Error("Thiếu đơn vị gia công.")
    if not product_code:
        raise Phase3Error("Thiếu mã SP.")
    if qty is None or qty <= 0:
        raise Phase3Error("SL gia công phải > 0.")
    mo = None
    if production_order_id:
        mo = SxProductionOrder.objects.get(pk=production_order_id)
        if not product_name:
            product_name = mo.product_name
        if not product_code:
            product_code = mo.product_code
    order = SxSubcontractOrder.objects.create(
        code=(code or "").strip() or _next_code("GC", SxSubcontractOrder),
        production_order=mo,
        vendor_name=vendor_name,
        product_code=product_code,
        product_name=(product_name or "").strip(),
        process_name=(process_name or "").strip(),
        qty=qty.quantize(Decimal("0.01")),
        order_date=order_date or timezone.localdate(),
        due_date=due_date,
        status=SxSubcontractOrder.STATUS_DRAFT,
        notes=notes or "",
        is_demo=False,
    )
    for row in out_lines or []:
        code_m = (row.get("material_code") or "").strip()
        q = row.get("qty")
        if not code_m or q is None or Decimal(str(q)) <= 0:
            continue
        SxSubcontractMaterialLine.objects.create(
            order=order,
            direction=SxSubcontractMaterialLine.DIRECTION_OUT,
            material_code=code_m,
            material_name=(row.get("material_name") or "").strip(),
            qty=Decimal(str(q)).quantize(Decimal("0.01")),
            uom_label=(row.get("uom_label") or "SP").strip() or "SP",
            lot_code=(row.get("lot_code") or "").strip(),
            notes=(row.get("notes") or "").strip(),
        )
    return order


@transaction.atomic
def add_subcontract_material_line(
    *,
    order_id: int,
    direction: str,
    material_code: str,
    qty: Decimal,
    material_name: str = "",
    uom_label: str = "SP",
    lot_code: str = "",
    notes: str = "",
) -> SxSubcontractMaterialLine:
    order = SxSubcontractOrder.objects.select_for_update().get(pk=order_id)
    if order.status in {SxSubcontractOrder.STATUS_DONE, SxSubcontractOrder.STATUS_CANCELLED}:
        raise Phase3Error("Lệnh GC đã kết thúc.")
    material_code = (material_code or "").strip()
    if not material_code:
        raise Phase3Error("Thiếu mã NVL/BTP.")
    if qty is None or qty <= 0:
        raise Phase3Error("SL dòng phải > 0.")
    if direction not in {
        SxSubcontractMaterialLine.DIRECTION_OUT,
        SxSubcontractMaterialLine.DIRECTION_IN,
    }:
        raise Phase3Error("Hướng dòng không hợp lệ.")
    return SxSubcontractMaterialLine.objects.create(
        order=order,
        direction=direction,
        material_code=material_code,
        material_name=(material_name or "").strip(),
        qty=qty.quantize(Decimal("0.01")),
        uom_label=(uom_label or "SP").strip() or "SP",
        lot_code=(lot_code or "").strip(),
        notes=(notes or "").strip(),
    )


@transaction.atomic
def advance_subcontract_order(
    *,
    order_id: int,
    to_status: str,
    qty_received: Decimal | None = None,
    user=None,
    post_stock: bool = True,
) -> SxSubcontractOrder:
    order = SxSubcontractOrder.objects.select_for_update().get(pk=order_id)
    allowed = {
        SxSubcontractOrder.STATUS_DRAFT: {
            SxSubcontractOrder.STATUS_SENT,
            SxSubcontractOrder.STATUS_CANCELLED,
        },
        SxSubcontractOrder.STATUS_SENT: {
            SxSubcontractOrder.STATUS_RECEIVED,
            SxSubcontractOrder.STATUS_DONE,
            SxSubcontractOrder.STATUS_CANCELLED,
        },
        SxSubcontractOrder.STATUS_RECEIVED: {
            SxSubcontractOrder.STATUS_DONE,
            SxSubcontractOrder.STATUS_CANCELLED,
        },
    }
    if to_status not in allowed.get(order.status, set()):
        raise Phase3Error(f"Không chuyển {order.status} → {to_status}.")

    now = timezone.now()
    update_fields = ["status"]
    if to_status == SxSubcontractOrder.STATUS_SENT:
        if not order.material_lines.filter(direction=SxSubcontractMaterialLine.DIRECTION_OUT).exists():
            raise Phase3Error("Cần ít nhất 1 dòng xuất NVL/BTP trước khi gửi GC.")
        order.sent_at = now
        update_fields.append("sent_at")
    elif to_status == SxSubcontractOrder.STATUS_RECEIVED:
        recv = qty_received if qty_received is not None else order.qty
        if recv is None or recv <= 0:
            raise Phase3Error("SL nhận lại phải > 0.")
        order.qty_received = Decimal(str(recv)).quantize(Decimal("0.01"))
        order.received_at = now
        update_fields.extend(["qty_received", "received_at"])
    elif to_status == SxSubcontractOrder.STATUS_DONE:
        if order.qty_received <= 0:
            order.qty_received = order.qty
            update_fields.append("qty_received")
        if not order.received_at:
            order.received_at = now
            update_fields.append("received_at")

    order.status = to_status
    order.save(update_fields=update_fields)

    if post_stock:
        if to_status == SxSubcontractOrder.STATUS_SENT:
            _post_subcontract_stock_out(order=order, user=user)
        elif to_status == SxSubcontractOrder.STATUS_RECEIVED:
            _post_subcontract_stock_in(order=order, user=user)

    order.refresh_from_db()
    return order


def _resolve_gc_material(code: str):
    from kho_npl.models import Material

    mat = Material.objects.filter(code__iexact=(code or "").strip(), is_active=True).first()
    return mat


def _post_subcontract_stock_out(*, order: SxSubcontractOrder, user) -> None:
    """Xuất kho NPL các dòng OUT khi gửi GC — bắt buộc đủ tồn / mã kho."""
    if order.stock_issue_id:
        return
    from kho_npl.choices import ISSUE_TYPE_PRODUCTION
    from kho_npl.models import StockIssue, StockIssueLine
    from kho_npl.services.doc_numbers import next_issue_number
    from kho_npl.services.issues import post_stock_issue
    from san_xuat.services.dispatch import (
        DispatchError,
        _allocate_batches,
        _split_stock_locations,
    )

    out_lines = list(
        order.material_lines.filter(direction=SxSubcontractMaterialLine.DIRECTION_OUT)
    )
    if not out_lines:
        raise Phase3Error("Không có dòng xuất NVL/BTP để trừ kho.")

    issue_lines = []
    missing = []
    for row in out_lines:
        mat = _resolve_gc_material(row.material_code)
        if not mat:
            missing.append(row.material_code or "?")
            continue
        qty = (row.qty or Decimal("0")).quantize(Decimal("0.001"))
        if qty <= 0:
            continue
        try:
            loc_splits = _split_stock_locations(mat, qty)
            allocations = _allocate_batches(mat, qty)
        except DispatchError as exc:
            raise Phase3Error(str(exc)) from exc
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
                issue_lines.append((mat, location, batch, take))
                need -= take
                alloc_left -= take
                if alloc_left <= 0:
                    alloc_i += 1
                    alloc_left = (
                        allocations[alloc_i][1] if alloc_i < len(allocations) else Decimal("0")
                    )
    if missing:
        raise Phase3Error(
            "Mã NVL/BTP chưa có trong kho_npl: " + ", ".join(missing)
        )
    if not issue_lines:
        raise Phase3Error("Không tạo được dòng xuất kho — kiểm tra số lượng dòng OUT.")

    issue = StockIssue.objects.create(
        number=next_issue_number(),
        issue_date=timezone.localdate(),
        issue_type=ISSUE_TYPE_PRODUCTION,
        production_order=order.production_order.code if order.production_order_id else order.code,
        product_code=order.product_code,
        issued_by=user,
        created_by=user,
        recipient=user,
        notes=f"Gửi GC {order.code} — {order.vendor_name}",
    )
    for mat, location, batch, qty_take in issue_lines:
        StockIssueLine.objects.create(
            issue=issue,
            material=mat,
            location=location,
            batch=batch,
            quantity=qty_take,
        )
    try:
        post_stock_issue(issue, user)
    except Exception as exc:
        order.stock_issue = issue
        order.save(update_fields=["stock_issue"])
        raise Phase3Error(f"Không post được phiếu xuất kho: {exc}") from exc
    issue.refresh_from_db()
    order.stock_issue = issue
    order.save(update_fields=["stock_issue"])


def _post_subcontract_stock_in(*, order: SxSubcontractOrder, user) -> None:
    """Nhận về: phiếu điều chỉnh +qty — bắt buộc có mã NVL trong kho."""
    if order.stock_adjustment_id:
        return
    from kho_npl.choices import ADJUST_STATUS_PENDING
    from kho_npl.models import StockAdjustment, StockAdjustmentLine, StockBalance
    from kho_npl.services.adjustments import approve_stock_adjustment
    from kho_npl.services.doc_numbers import next_adjustment_number
    from san_xuat.services.dispatch import _default_stock_location, _surplus_batch_for_material

    in_lines = list(
        order.material_lines.filter(direction=SxSubcontractMaterialLine.DIRECTION_IN)
    )
    rows = []
    missing = []
    if in_lines:
        for row in in_lines:
            mat = _resolve_gc_material(row.material_code)
            if not mat:
                missing.append(row.material_code or "?")
                continue
            if (row.qty or 0) > 0:
                rows.append((mat, row.qty))
    else:
        mat = _resolve_gc_material(order.product_code)
        if not mat:
            raise Phase3Error(
                f"Mã nhận {order.product_code} chưa có trong kho_npl — thêm dòng IN hoặc tạo NVL."
            )
        if (order.qty_received or 0) > 0:
            rows.append((mat, order.qty_received))
    if missing:
        raise Phase3Error("Mã nhận chưa có trong kho_npl: " + ", ".join(missing))
    if not rows:
        raise Phase3Error("Không có dòng nhận về để cộng kho.")

    location = _default_stock_location()
    adj = StockAdjustment.objects.create(
        number=next_adjustment_number(),
        adjust_date=timezone.localdate(),
        reason=f"Nhận về GC {order.code}",
        proposed_by=user,
        status=ADJUST_STATUS_PENDING,
    )
    for mat, qty in rows:
        bal = StockBalance.objects.filter(material=mat, location=location).first()
        system_qty = bal.quantity if bal else Decimal("0")
        actual = (system_qty + Decimal(str(qty))).quantize(Decimal("0.001"))
        batch = _surplus_batch_for_material(mat)
        StockAdjustmentLine.objects.create(
            adjustment=adj,
            material=mat,
            location=location,
            batch=batch,
            system_qty=system_qty.quantize(Decimal("0.001")),
            actual_qty=actual,
        )
    try:
        approve_stock_adjustment(adj, user)
    except Exception as exc:
        order.stock_adjustment = adj
        order.save(update_fields=["stock_adjustment"])
        raise Phase3Error(f"Không duyệt được phiếu điều chỉnh kho: {exc}") from exc
    order.stock_adjustment = adj
    order.save(update_fields=["stock_adjustment"])


@dataclass
class PieceRateRow:
    process_name: str
    team_label: str
    qty_good: Decimal
    piece_rate: Decimal
    amount: Decimal
    production_order_code: str
    stat_code: str
    employee_code: str = ""
    employee_name: str = ""
    hr_mapped: bool = False


def compute_piece_rate_pay(
    *,
    date_from=None,
    date_to=None,
    production_order_id: int | None = None,
) -> list[PieceRateRow]:
    """Lương SP = Thống kê sản xuất confirmed.qty_good × ProcessStep.piece_rate (khớp tên CĐ)."""
    from san_xuat.hub_models import SxTeamHrMap
    from san_xuat.models import ProcessStep

    qs = SxProductionStat.objects.filter(
        is_demo=False,
        status=SxProductionStat.STATUS_CONFIRMED,
    ).select_related("production_order", "production_order__bom_version")
    if date_from:
        qs = qs.filter(stat_date__gte=date_from)
    if date_to:
        qs = qs.filter(stat_date__lte=date_to)
    if production_order_id:
        qs = qs.filter(production_order_id=production_order_id)

    hr_map = {
        m.team_label.strip().lower(): m
        for m in SxTeamHrMap.objects.filter(is_active=True, is_demo=False)
        if (m.team_label or "").strip()
    }

    rows: list[PieceRateRow] = []
    for stat in qs.order_by("-stat_date", "-pk")[:500]:
        rate = Decimal("0")
        bom = stat.production_order.bom_version if stat.production_order_id else None
        if bom and stat.process_name:
            step = (
                ProcessStep.objects.filter(bom=bom, process_name__iexact=stat.process_name)
                .order_by("sequence")
                .first()
            )
            if step:
                rate = step.piece_rate or Decimal("0")
        qty = stat.qty_good or Decimal("0")
        if qty <= 0 or rate <= 0:
            continue
        team = (stat.team_label or "").strip()
        mapped = hr_map.get(team.lower()) if team else None
        rows.append(
            PieceRateRow(
                process_name=stat.process_name,
                team_label=team,
                qty_good=qty,
                piece_rate=rate,
                amount=(qty * rate).quantize(Decimal("0.01")),
                production_order_code=stat.production_order.code if stat.production_order_id else "",
                stat_code=stat.code,
                employee_code=(mapped.employee_code if mapped else "") or "",
                employee_name=(mapped.employee_name if mapped else "") or "",
                hr_mapped=bool(mapped and mapped.employee_code),
            )
        )
    return rows


# --- Truy xuất nguồn gốc ---


@dataclass
class TraceEvent:
    when: object
    kind: str
    label: str
    detail: str = ""
    url_name: str = ""
    url_pk: int | None = None


@dataclass
class TraceResult:
    query: str
    mo: SxProductionOrder | None = None
    fg_receipts: list = field(default_factory=list)
    material_issues: list = field(default_factory=list)
    issue_batches: list = field(default_factory=list)
    packing: list = field(default_factory=list)
    stats: list = field(default_factory=list)
    qc_requests: list = field(default_factory=list)
    work_assignments: list = field(default_factory=list)
    subcontract_orders: list = field(default_factory=list)
    timeline: list = field(default_factory=list)
    reverse_batch: bool = False
    message: str = ""


def models_q_or_code(q: str):
    return Q(code__iexact=q) | Q(kv_purchase_code__iexact=q)


def _resolve_mo_from_query(q: str, result: TraceResult) -> SxProductionOrder | None:
    mo = SxProductionOrder.objects.filter(is_demo=False, code__iexact=q).first()
    if mo:
        return mo

    fg = (
        SxFgReceiptRequest.objects.filter(is_demo=False)
        .filter(models_q_or_code(q))
        .select_related("production_order")
        .first()
    )
    if fg and fg.production_order_id:
        result.fg_receipts = [fg]
        return fg.production_order

    pack = (
        SxPackingRecord.objects.filter(is_demo=False)
        .filter(Q(code__iexact=q) | Q(lot_code__iexact=q))
        .select_related("production_order")
        .first()
    )
    if pack and pack.production_order_id:
        return pack.production_order

    # Yêu cầu xuất code
    ycx = (
        SxMaterialIssueRequest.objects.filter(is_demo=False, code__iexact=q)
        .select_related("production_order")
        .first()
    )
    if ycx and ycx.production_order_id:
        return ycx.production_order

    # Reverse: NPL batch code → MOs that issued that batch
    from kho_npl.models import StockIssueLine

    issue_lines = (
        StockIssueLine.objects.filter(batch__code__iexact=q)
        .select_related("issue", "batch", "material")
        .order_by("-id")[:50]
    )
    if issue_lines:
        issue_ids = {ln.issue_id for ln in issue_lines if ln.issue_id}
        ycx_list = list(
            SxMaterialIssueRequest.objects.filter(is_demo=False, stock_issue_id__in=issue_ids)
            .select_related("production_order")
            .order_by("-request_date")
        )
        if ycx_list:
            result.reverse_batch = True
            result.material_issues = ycx_list
            # Prefer first MO; still list all batches
            for ln in issue_lines:
                ycx_match = next((y for y in ycx_list if y.stock_issue_id == ln.issue_id), None)
                result.issue_batches.append({
                    "ycx": ycx_match.code if ycx_match else "—",
                    "issue_number": ln.issue.number if ln.issue_id else "—",
                    "material_code": ln.material.code if ln.material_id else "",
                    "material_name": ln.material.name if ln.material_id else "",
                    "qty": ln.quantity,
                    "batch_code": ln.batch.code if ln.batch_id else "—",
                    "location": getattr(ln.location, "code", "—") if getattr(ln, "location_id", None) else "—",
                })
            mo_cand = next((y.production_order for y in ycx_list if y.production_order_id), None)
            return mo_cand

    gc = (
        SxSubcontractOrder.objects.filter(is_demo=False, code__iexact=q)
        .select_related("production_order")
        .first()
    )
    if gc and gc.production_order_id:
        return gc.production_order

    gv = (
        SxWorkAssignment.objects.filter(is_demo=False, code__iexact=q)
        .select_related("production_order")
        .first()
    )
    if gv and gv.production_order_id:
        return gv.production_order

    return None


def _build_timeline(result: TraceResult) -> list[TraceEvent]:
    events: list[TraceEvent] = []
    mo = result.mo
    if not mo:
        return events

    events.append(TraceEvent(
        when=mo.created_at if hasattr(mo, "created_at") else mo.order_date,
        kind="mo",
        label=f"Lệnh sản xuất {mo.code}",
        detail=f"{mo.product_code} · SL {mo.qty} · {mo.get_status_display()}",
        url_name="san_xuat:dispatch_mo_detail",
        url_pk=mo.pk,
    ))

    for req in result.material_issues:
        events.append(TraceEvent(
            when=req.request_date,
            kind="ycx",
            label=f"Yêu cầu xuất {req.code}",
            detail=str(getattr(req, "status", "") or "—"),
            url_name="san_xuat:dispatch_material_issue_req_detail",
            url_pk=req.pk,
        ))

    for st in result.stats:
        events.append(TraceEvent(
            when=st.stat_date,
            kind="tksx",
            label=f"Thống kê sản xuất {st.code}",
            detail=f"{st.process_name or '—'} · đạt {st.qty_good} / lỗi {st.qty_defect}",
            url_name="san_xuat:dispatch_prod_stats_detail",
            url_pk=st.pk,
        ))

    for qc in result.qc_requests:
        events.append(TraceEvent(
            when=getattr(qc, "request_date", None) or getattr(qc, "created_at", None),
            kind="qc",
            label=f"YCKT {qc.code}",
            detail=str(qc.status or "—"),
            url_name="san_xuat:qc_request_detail",
            url_pk=qc.pk,
        ))

    for fg in result.fg_receipts:
        events.append(TraceEvent(
            when=fg.request_date,
            kind="ycntp",
            label=f"Yêu cầu nhập thành phẩm {fg.code}",
            detail=(f"KV {fg.kv_purchase_code}" if fg.kv_purchase_code else fg.get_status_display()),
            url_name="san_xuat:dispatch_fg_receipt_req_detail",
            url_pk=fg.pk,
        ))

    for p in result.packing:
        events.append(TraceEvent(
            when=p.pack_date,
            kind="pack",
            label=f"ĐG {p.code}",
            detail=f"SL {p.qty} · lô {p.lot_code or '—'}",
            url_name="san_xuat:packing_detail",
            url_pk=p.pk,
        ))

    for gv in result.work_assignments:
        events.append(TraceEvent(
            when=gv.created_at,
            kind="gv",
            label=f"GV {gv.code}",
            detail=f"{gv.title} · {gv.get_status_display()}",
            url_name="san_xuat:work_assignment_list",
            url_pk=None,
        ))

    for gc in result.subcontract_orders:
        events.append(TraceEvent(
            when=gc.order_date,
            kind="gc",
            label=f"GC {gc.code}",
            detail=f"{gc.vendor_name} · {gc.get_status_display()}",
            url_name="san_xuat:subcontract_detail",
            url_pk=gc.pk,
        ))

    def _sort_key(ev: TraceEvent):
        w = ev.when
        if w is None:
            return timezone.now().date().isoformat()
        if hasattr(w, "isoformat"):
            return w.isoformat()
        return str(w)

    events.sort(key=_sort_key)
    return events


def trace_production(*, query: str) -> TraceResult:
    """Tra cứu chuỗi: mã Lệnh sản xuất / Yêu cầu nhập thành phẩm / KV / lô ĐG / Yêu cầu xuất / lô NPL / GC / GV."""
    q = (query or "").strip()
    result = TraceResult(query=q)
    if not q:
        result.message = "Nhập mã LSX, YCNTP, phiếu KV, YCX, lô ĐG, lô NPL, GC hoặc GV."
        return result

    mo = _resolve_mo_from_query(q, result)
    if not mo:
        result.message = f"Không tìm thấy chuỗi truy xuất cho «{q}»."
        return result

    result.mo = mo
    if not result.fg_receipts:
        result.fg_receipts = list(
            SxFgReceiptRequest.objects.filter(is_demo=False, production_order=mo).order_by("-request_date")
        )
    result.packing = list(
        SxPackingRecord.objects.filter(is_demo=False, production_order=mo)
        .prefetch_related("lines")
        .order_by("-pack_date")
    )
    if not result.material_issues:
        result.material_issues = list(
            SxMaterialIssueRequest.objects.filter(is_demo=False, production_order=mo)
            .select_related("stock_issue")
            .prefetch_related("lines")
            .order_by("-request_date")
        )
    if not result.issue_batches:
        batches: list[dict] = []
        for req in result.material_issues:
            if not req.stock_issue_id:
                continue
            for line in req.stock_issue.lines.select_related("material", "batch", "location").all():
                batches.append({
                    "ycx": req.code,
                    "issue_number": req.stock_issue.number,
                    "material_code": line.material.code if line.material_id else "",
                    "material_name": line.material.name if line.material_id else "",
                    "qty": line.quantity,
                    "batch_code": line.batch.code if line.batch_id else "—",
                    "location": line.location.code if line.location_id else "—",
                })
        result.issue_batches = batches

    result.stats = list(
        SxProductionStat.objects.filter(is_demo=False, production_order=mo).order_by("stat_date", "pk")
    )
    result.qc_requests = list(
        SxQcRequest.objects.filter(is_demo=False, production_order=mo).order_by("-pk")[:50]
    )
    result.work_assignments = list(
        SxWorkAssignment.objects.filter(is_demo=False, production_order=mo)
        .select_related("work_center", "work_task", "assignee")
        .order_by("-created_at")
    )
    result.subcontract_orders = list(
        SxSubcontractOrder.objects.filter(is_demo=False, production_order=mo)
        .prefetch_related("material_lines")
        .order_by("-order_date")
    )
    result.timeline = _build_timeline(result)
    return result


# --- Báo cáo vận hành ---


@dataclass
class OpsReport:
    date_from: object
    date_to: object
    product_code: str = ""
    process_name: str = ""
    team_label: str = ""
    mo_by_status: list = field(default_factory=list)
    qty_good: Decimal = field(default_factory=lambda: Decimal("0"))
    qty_defect: Decimal = field(default_factory=lambda: Decimal("0"))
    open_alerts: int = 0
    packing_qty: Decimal = field(default_factory=lambda: Decimal("0"))
    subcontract_open: int = 0
    work_open: int = 0
    team_output: list = field(default_factory=list)
    process_output: list = field(default_factory=list)
    product_output: list = field(default_factory=list)
    production_by_day: list = field(default_factory=list)
    downtime_by_reason: list = field(default_factory=list)
    downtime_minutes: int = 0
    ycx_count: int = 0
    ycntp_count: int = 0
    mo_open: int = 0
    mo_done: int = 0
    mo_rows: list = field(default_factory=list)
    packing_rows: list = field(default_factory=list)
    defect_rate: float = 0.0
    report_catalog: list = field(default_factory=list)


def build_ops_report(
    *,
    date_from,
    date_to,
    product_code: str = "",
    process_name: str = "",
    team_label: str = "",
) -> OpsReport:
    from datetime import timedelta

    product_code = (product_code or "").strip()
    process_name = (process_name or "").strip()
    team_label = (team_label or "").strip()
    report = OpsReport(
        date_from=date_from,
        date_to=date_to,
        product_code=product_code,
        process_name=process_name,
        team_label=team_label,
    )

    mo_qs = SxProductionOrder.objects.filter(is_demo=False)
    if product_code:
        mo_qs = mo_qs.filter(product_code__icontains=product_code)
    if team_label:
        mo_qs = mo_qs.filter(team_label__icontains=team_label)

    open_statuses = [
        SxProductionOrder.STATUS_DRAFT,
        SxProductionOrder.STATUS_RELEASED,
        SxProductionOrder.STATUS_IN_PROGRESS,
    ]
    report.mo_open = mo_qs.filter(status__in=open_statuses).count()
    report.mo_done = mo_qs.filter(status=SxProductionOrder.STATUS_DONE).count()

    labels = dict(SxProductionOrder.STATUS_CHOICES)
    counts = {r["status"]: r["c"] for r in mo_qs.values("status").annotate(c=Count("id"))}
    report.mo_by_status = [
        {"status": k, "label": labels.get(k, k), "count": counts.get(k, 0)}
        for k, _ in SxProductionOrder.STATUS_CHOICES
    ]
    report.mo_rows = list(
        mo_qs.exclude(status=SxProductionOrder.STATUS_CANCELLED)
        .order_by("-order_date", "-pk")[:80]
    )

    stats = SxProductionStat.objects.filter(
        is_demo=False,
        status=SxProductionStat.STATUS_CONFIRMED,
        stat_date__gte=date_from,
        stat_date__lte=date_to,
    )
    if product_code:
        stats = stats.filter(production_order__product_code__icontains=product_code)
    if process_name:
        stats = stats.filter(process_name__icontains=process_name)
    if team_label:
        stats = stats.filter(team_label__icontains=team_label)

    agg = stats.aggregate(
        good=Coalesce(Sum("qty_good"), Decimal("0")),
        defect=Coalesce(Sum("qty_defect"), Decimal("0")),
    )
    report.qty_good = Decimal(str(agg["good"] or 0))
    report.qty_defect = Decimal(str(agg["defect"] or 0))
    total = report.qty_good + report.qty_defect
    report.defect_rate = float(report.qty_defect / total * 100) if total else 0.0

    # Sản lượng theo ngày
    day_map = {
        row["day"]: (
            Decimal(str(row["good"] or 0)),
            Decimal(str(row["defect"] or 0)),
        )
        for row in (
            stats.annotate(day=TruncDate("stat_date"))
            .values("day")
            .annotate(
                good=Coalesce(Sum("qty_good"), Decimal("0")),
                defect=Coalesce(Sum("qty_defect"), Decimal("0")),
            )
        )
        if row["day"]
    }
    span_days = (date_to - date_from).days + 1
    if span_days <= 62:
        cursor = date_from
        while cursor <= date_to:
            good, defect = day_map.get(cursor, (Decimal("0"), Decimal("0")))
            report.production_by_day.append({
                "date": cursor.isoformat(),
                "label": cursor.strftime("%d/%m"),
                "qty_good": float(good),
                "qty_defect": float(defect),
            })
            cursor += timedelta(days=1)
    else:
        for day in sorted(day_map.keys()):
            good, defect = day_map[day]
            report.production_by_day.append({
                "date": day.isoformat(),
                "label": day.strftime("%d/%m"),
                "qty_good": float(good),
                "qty_defect": float(defect),
            })

    alert_qs = SxQcAlert.objects.filter(is_demo=False, status=SxQcAlert.STATUS_OPEN)
    if product_code:
        alert_qs = alert_qs.filter(production_order__product_code__icontains=product_code)
    report.open_alerts = alert_qs.count()

    pack_qs = SxPackingRecord.objects.filter(
        is_demo=False,
        status=SxPackingRecord.STATUS_CONFIRMED,
        pack_date__gte=date_from,
        pack_date__lte=date_to,
    )
    if product_code:
        pack_qs = pack_qs.filter(production_order__product_code__icontains=product_code)
    pack_agg = pack_qs.aggregate(q=Coalesce(Sum("qty"), Decimal("0")))
    report.packing_qty = Decimal(str(pack_agg["q"] or 0))
    report.packing_rows = list(pack_qs.select_related("production_order").order_by("-pack_date")[:40])

    report.subcontract_open = SxSubcontractOrder.objects.filter(
        is_demo=False,
        status__in=[
            SxSubcontractOrder.STATUS_DRAFT,
            SxSubcontractOrder.STATUS_SENT,
            SxSubcontractOrder.STATUS_RECEIVED,
        ],
    ).count()
    report.work_open = SxWorkAssignment.objects.filter(
        is_demo=False, status=SxWorkAssignment.STATUS_OPEN,
    ).count()

    ycx_qs = SxMaterialIssueRequest.objects.filter(
        is_demo=False,
        request_date__gte=date_from,
        request_date__lte=date_to,
    )
    if product_code:
        ycx_qs = ycx_qs.filter(production_order__product_code__icontains=product_code)
    report.ycx_count = ycx_qs.count()

    ycntp_qs = SxFgReceiptRequest.objects.filter(
        is_demo=False,
        request_date__gte=date_from,
        request_date__lte=date_to,
    )
    if product_code:
        ycntp_qs = ycntp_qs.filter(production_order__product_code__icontains=product_code)
    report.ycntp_count = ycntp_qs.count()

    report.team_output = []
    for row in (
        stats.exclude(team_label="")
        .values("team_label")
        .annotate(
            good=Coalesce(Sum("qty_good"), Decimal("0")),
            defect=Coalesce(Sum("qty_defect"), Decimal("0")),
        )
        .order_by("-good")[:15]
    ):
        good = float(row["good"] or 0)
        defect = float(row["defect"] or 0)
        tot = good + defect
        report.team_output.append({
            "team_label": row["team_label"] or "—",
            "qty_good": good,
            "qty_defect": defect,
            "defect_rate": round(defect / tot * 100, 1) if tot else 0.0,
        })

    report.process_output = []
    for row in (
        stats.exclude(process_name="")
        .values("process_name")
        .annotate(
            good=Coalesce(Sum("qty_good"), Decimal("0")),
            defect=Coalesce(Sum("qty_defect"), Decimal("0")),
        )
        .order_by("-good")[:15]
    ):
        good = float(row["good"] or 0)
        defect = float(row["defect"] or 0)
        tot = good + defect
        report.process_output.append({
            "process_name": row["process_name"],
            "qty_good": good,
            "qty_defect": defect,
            "defect_rate": round(defect / tot * 100, 1) if tot else 0.0,
        })

    report.product_output = []
    for row in (
        stats.values(
            product_code=F("production_order__product_code"),
            product_name=F("production_order__product_name"),
        )
        .annotate(
            good=Coalesce(Sum("qty_good"), Decimal("0")),
            defect=Coalesce(Sum("qty_defect"), Decimal("0")),
        )
        .order_by("-good")[:15]
    ):
        good = float(row["good"] or 0)
        defect = float(row["defect"] or 0)
        tot = good + defect
        report.product_output.append({
            "product_code": row["product_code"] or "—",
            "product_name": row["product_name"] or "",
            "qty_good": good,
            "qty_defect": defect,
            "defect_rate": round(defect / tot * 100, 1) if tot else 0.0,
        })

    dt_qs = SxDowntimeEvent.objects.filter(
        is_demo=False,
        event_date__gte=date_from,
        event_date__lte=date_to,
    )
    if team_label:
        dt_qs = dt_qs.filter(team_label__icontains=team_label)
    if product_code:
        dt_qs = dt_qs.filter(production_order__product_code__icontains=product_code)
    report.downtime_minutes = int(
        dt_qs.aggregate(m=Coalesce(Sum("minutes"), 0))["m"] or 0
    )
    report.downtime_by_reason = []
    for row in (
        dt_qs.values("reason")
        .annotate(minutes=Coalesce(Sum("minutes"), 0), events=Count("id"))
        .order_by("-minutes")[:12]
    ):
        mins = int(row["minutes"] or 0)
        report.downtime_by_reason.append({
            "reason": row["reason"] or "—",
            "minutes": mins,
            "events": row["events"],
            "pct": round(mins / report.downtime_minutes * 100, 1) if report.downtime_minutes else 0.0,
        })

    # Danh mục báo cáo kiểu AMIS reportlist
    report.report_catalog = [
        {
            "code": "SL-NGAY",
            "name": "Sản lượng theo ngày",
            "group": "Sản xuất",
            "tab": "theo-ngay",
            "metric": f"{float(report.qty_good):,.0f} đạt",
        },
        {
            "code": "SL-SP",
            "name": "Sản lượng theo sản phẩm",
            "group": "Sản xuất",
            "tab": "theo-sp",
            "metric": f"{len(report.product_output)} SP",
        },
        {
            "code": "SL-TO",
            "name": "Sản lượng theo tổ / chuyền",
            "group": "Sản xuất",
            "tab": "theo-to",
            "metric": f"{len(report.team_output)} tổ",
        },
        {
            "code": "SL-CD",
            "name": "Sản lượng theo công đoạn",
            "group": "Sản xuất",
            "tab": "theo-to",
            "metric": f"{len(report.process_output)} CĐ",
        },
        {
            "code": "LSX-TT",
            "name": "Lệnh sản xuất theo trạng thái",
            "group": "Điều phối",
            "tab": "lenh-sx",
            "metric": f"{report.mo_open} mở / {report.mo_done} xong",
        },
        {
            "code": "DG-KY",
            "name": "Đóng gói trong kỳ",
            "group": "Kho thành phẩm",
            "tab": "dong-goi",
            "metric": f"{float(report.packing_qty):,.0f}",
        },
        {
            "code": "DUNG-CHUYEN",
            "name": "Dừng chuyền / OEE",
            "group": "Vận hành",
            "tab": "dung-chuyen",
            "metric": f"{report.downtime_minutes:,} phút",
        },
        {
            "code": "YCX-YCNTP",
            "name": "Xuất NVL / nhập thành phẩm",
            "group": "Kho",
            "tab": "kho",
            "metric": f"YCX {report.ycx_count} · YCNTP {report.ycntp_count}",
        },
    ]
    return report


def export_ops_report_csv(*, report: OpsReport) -> HttpResponse:
    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Báo cáo vận hành SX", f"{report.date_from} → {report.date_to}"])
    writer.writerow([
        "SP lọc", report.product_code or "—",
        "Công đoạn", report.process_name or "—",
        "Tổ", report.team_label or "—",
    ])
    writer.writerow([])
    writer.writerow(["KPI", "Giá trị"])
    writer.writerow(["SL đạt", report.qty_good])
    writer.writerow(["SL lỗi", report.qty_defect])
    writer.writerow(["Tỷ lệ lỗi %", f"{report.defect_rate:.2f}"])
    writer.writerow(["QC mở", report.open_alerts])
    writer.writerow(["Đóng gói", report.packing_qty])
    writer.writerow(["GC mở", report.subcontract_open])
    writer.writerow(["Giao việc mở", report.work_open])
    writer.writerow(["YCX trong kỳ", report.ycx_count])
    writer.writerow(["YCNTP trong kỳ", report.ycntp_count])
    writer.writerow(["Dừng chuyền (phút)", report.downtime_minutes])
    writer.writerow([])
    writer.writerow(["Ngày", "Đạt", "Lỗi"])
    for row in report.production_by_day:
        writer.writerow([row["label"], row["qty_good"], row["qty_defect"]])
    writer.writerow([])
    writer.writerow(["Tổ", "SL đạt", "SL lỗi", "% lỗi"])
    for row in report.team_output:
        writer.writerow([row["team_label"], row["qty_good"], row["qty_defect"], row["defect_rate"]])
    writer.writerow([])
    writer.writerow(["Công đoạn", "Đạt", "Lỗi", "% lỗi"])
    for row in report.process_output:
        writer.writerow([row["process_name"], row["qty_good"], row["qty_defect"], row["defect_rate"]])
    writer.writerow([])
    writer.writerow(["Mã SP", "Tên", "Đạt", "Lỗi", "% lỗi"])
    for row in report.product_output:
        writer.writerow([
            row["product_code"], row["product_name"],
            row["qty_good"], row["qty_defect"], row["defect_rate"],
        ])
    writer.writerow([])
    writer.writerow(["LSX", "SP", "SL", "Đã làm", "TT"])
    for mo in report.mo_rows:
        writer.writerow([mo.code, mo.product_code, mo.qty, mo.qty_done, mo.get_status_display()])

    return HttpResponse(
        "\ufeff" + buf.getvalue(),
        content_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="ops-report-{report.date_from}-{report.date_to}.csv"'
            ),
        },
    )
