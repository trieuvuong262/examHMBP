"""NCR / rework / scrap / remake từ cảnh báo QC."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from san_xuat.hub_models import (
    SxNcrCase,
    SxProductionOrder,
    SxQcAlert,
)
from san_xuat.services.dispatch import create_production_stat, confirm_stat, DispatchError
from san_xuat.services.qc import acknowledge_alert, QcError


class NcrError(Exception):
    pass


def _next_ncr_code() -> str:
    from san_xuat.services.sx_settings import sx_prefix

    year = timezone.localdate().year
    prefix = f"{sx_prefix('ncr')}-{year}-"
    last = (
        SxNcrCase.objects.filter(code__startswith=prefix)
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
def create_ncr_from_alert(
    *,
    alert_id: int,
    disposition: str,
    qty: Decimal | None = None,
    notes: str = "",
) -> SxNcrCase:
    alert = SxQcAlert.objects.select_related("production_order").select_for_update().get(pk=alert_id)
    if alert.status == SxQcAlert.STATUS_CLOSED:
        raise NcrError("Cảnh báo đã đóng.")
    qty_val = qty if qty is not None else (alert.qty_defect or Decimal("0"))
    if qty_val <= 0:
        qty_val = Decimal("1")
    if disposition not in dict(SxNcrCase.DISP_CHOICES):
        raise NcrError("Disposition không hợp lệ.")

    case = SxNcrCase.objects.create(
        code=_next_ncr_code(),
        alert=alert,
        production_order=alert.production_order,
        disposition=disposition,
        qty=qty_val,
        process_name=alert.process_name or "",
        notes=notes or "",
        status=SxNcrCase.STATUS_DRAFT,
        is_demo=False,
    )
    return case


@transaction.atomic
def confirm_ncr(*, ncr_id: int, user=None) -> SxNcrCase:
    case = (
        SxNcrCase.objects.select_for_update()
        .select_related("production_order", "alert")
        .get(pk=ncr_id)
    )
    if case.status not in (SxNcrCase.STATUS_DRAFT,):
        raise NcrError("NCR không ở trạng thái nháp.")

    mo = case.production_order
    if case.disposition == SxNcrCase.DISP_REWORK:
        # Tạo Thống kê sản xuất rework (draft → confirm) ghi nhận SL sửa = qty (good)
        try:
            stat = create_production_stat(
                production_order_id=mo.pk,
                stat_date=timezone.localdate(),
                process_name=case.process_name or "Rework",
                qty_good=case.qty,
                qty_defect=Decimal("0"),
                team_label="Rework",
                notes=f"NCR {case.code} rework",
            )
            try:
                confirm_stat(stat_id=stat.pk)
            except DispatchError:
                pass
            case.rework_stat = stat
        except DispatchError as exc:
            raise NcrError(str(exc)) from exc

    elif case.disposition == SxNcrCase.DISP_REMAKE:
        # Lệnh sản xuất mẫu tái SX từ NCR
        remake = SxProductionOrder.objects.create(
            code=_next_remake_mo_code(mo),
            product_code=mo.product_code,
            product_name=mo.product_name,
            bom_version=mo.bom_version,
            qty=case.qty,
            order_date=timezone.localdate(),
            due_date=mo.due_date,
            team_label=mo.team_label,
            status=SxProductionOrder.STATUS_DRAFT,
            is_sample=True,
            notes=f"Tái SX từ NCR {case.code} / Lệnh sản xuất gốc {mo.code}",
            is_demo=False,
        )
        case.remake_order = remake

    elif case.disposition == SxNcrCase.DISP_SCRAP:
        case.notes = (case.notes + " · Phế ghi nhận NCR").strip(" ·")

    # use_as_is: chỉ đóng

    case.status = SxNcrCase.STATUS_CONFIRMED
    case.confirmed_at = timezone.now()
    case.save()

    if case.alert_id and case.alert.status == SxQcAlert.STATUS_OPEN:
        try:
            acknowledge_alert(alert_id=case.alert_id)
        except QcError:
            pass

    case.status = SxNcrCase.STATUS_DONE
    case.save(update_fields=["status"])
    return case


def _next_remake_mo_code(mo: SxProductionOrder) -> str:
    year = timezone.localdate().year
    prefix = f"LSX-RM-{year}-"
    last = (
        SxProductionOrder.objects.filter(code__startswith=prefix)
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
