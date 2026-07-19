"""Shop floor — xác nhận CĐ nhanh bằng mã LSX / TKSX / quét."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from san_xuat.hub_models import SxProductionOrder, SxProductionStat
from san_xuat.models import ProcessStep as Step
from san_xuat.services.dispatch import (
    DispatchError,
    confirm_stat,
    create_production_stat,
)


class ShopFloorError(Exception):
    pass


def lookup_mo(code: str) -> SxProductionOrder | None:
    code = (code or "").strip()
    if not code:
        return None
    return (
        SxProductionOrder.objects.filter(is_demo=False, code__iexact=code)
        .select_related("bom_version")
        .first()
    )


def lookup_stat(code: str) -> SxProductionStat | None:
    code = (code or "").strip()
    if not code:
        return None
    return (
        SxProductionStat.objects.filter(is_demo=False, code__iexact=code)
        .select_related("production_order")
        .first()
    )


@transaction.atomic
def quick_confirm_scan(
    *,
    scan: str,
    process_name: str = "",
    qty_good: Decimal = Decimal("1"),
    team_label: str = "",
) -> dict:
    """
    Quét mã:
    - TKSX nháp → confirm
    - LSX → tạo + confirm TKSX nhanh (cần process_name hoặc lấy CĐ đầu BOM)
    """
    scan = (scan or "").strip()
    if not scan:
        raise ShopFloorError("Nhập / quét mã LSX hoặc TKSX.")

    stat = lookup_stat(scan)
    if stat:
        if stat.status == SxProductionStat.STATUS_CONFIRMED:
            raise ShopFloorError(f"TKSX {stat.code} đã xác nhận.")
        confirm_stat(stat_id=stat.pk)
        return {"kind": "stat_confirm", "stat": stat, "mo": stat.production_order}

    mo = lookup_mo(scan)
    if not mo:
        raise ShopFloorError(f"Không tìm thấy LSX/TKSX: {scan}")
    if mo.status not in (
        SxProductionOrder.STATUS_RELEASED,
        SxProductionOrder.STATUS_IN_PROGRESS,
        SxProductionOrder.STATUS_DONE,
    ):
        raise ShopFloorError("LSX chưa phát hành.")

    pname = (process_name or "").strip()
    if not pname and mo.bom_version_id:
        step = Step.objects.filter(bom=mo.bom_version).order_by("sequence").first()
        if step:
            pname = step.process_name
            if not team_label and step.work_center_id:
                team_label = step.work_center.team_label or step.work_center.name
    if not pname:
        raise ShopFloorError("Cần chọn công đoạn (BOM chưa có CĐ).")

    try:
        stat = create_production_stat(
            production_order_id=mo.pk,
            stat_date=timezone.localdate(),
            process_name=pname,
            qty_good=qty_good or Decimal("1"),
            qty_defect=Decimal("0"),
            team_label=team_label or mo.team_label,
            notes="Shop floor scan",
        )
        confirm_stat(stat_id=stat.pk)
    except DispatchError as exc:
        raise ShopFloorError(str(exc)) from exc

    return {"kind": "mo_stat", "stat": stat, "mo": mo}
