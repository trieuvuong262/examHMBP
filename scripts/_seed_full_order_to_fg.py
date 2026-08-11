"""Seed 1 đơn hàng đầy đủ trên VPS: ĐĐH → LSX → tiến độ mọi công đoạn → YCNTP nháp.

Dừng ở nhập kho thành phẩm (không gửi KV / không hoàn thành phiếu nhập).
Chạy:
  docker compose exec -T web python manage.py shell < scripts/_seed_full_order_to_fg.py
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from kiotviet.models import KvBranch
from san_xuat.hub_models import (
    SxFgReceiptRequest,
    SxMoProcessStep,
    SxProductionOrder,
    SxProductionOrderLine,
    SxProductionStat,
    SxQcInspection,
    SxQcRequest,
    SxSalesOrder,
    SxSalesOrderLine,
)
from san_xuat.models import BomVersion, ProductTechDoc
from san_xuat.services.dispatch import (
    _recompute_mo_progress,
    create_fg_receipt_from_mo,
    fg_receipt_prefill,
)
from san_xuat.services.order_progress_sheet import (
    ensure_progress_work_centers,
    seed_order_plan_steps_from_template,
)
from san_xuat.services.progress_template import TEAM_SLUGS, progress_steps
from san_xuat.services.team_work import close_team_job, ensure_mo_step_for_template

DEMO_SO = "DH-2026-FULL-001"
DEMO_MO = "LSX-2026-FULL-001"
DEMO_QC = "YCKT-2026-FULL-001"
DEMO_PKT = "PKT-2026-FULL-001"
DEMO_FG = "YCNTP-2026-FULL-001"
DEMO_NOTE = "[FULL] Don hang day du — dung o nhap kho thanh pham"

STYLE = "JP-SET-SC-SP008146"
SIZE_QTY = [
    ("S", Decimal("20")),
    ("M", Decimal("30")),
    ("L", Decimal("30")),
    ("XL", Decimal("20")),
    ("XXL", Decimal("10")),
    ("XXXL", Decimal("10")),
]


def _wipe():
    mos = list(SxProductionOrder.objects.filter(code=DEMO_MO))
    for mo in mos:
        SxQcInspection.objects.filter(qc_request__production_order=mo).delete()
        SxQcInspection.objects.filter(code=DEMO_PKT).delete()
        SxQcRequest.objects.filter(production_order=mo).delete()
        SxQcRequest.objects.filter(code=DEMO_QC).delete()
        SxFgReceiptRequest.objects.filter(production_order=mo).delete()
        SxFgReceiptRequest.objects.filter(code=DEMO_FG).delete()
        mo.delete()
    SxSalesOrder.objects.filter(code=DEMO_SO).delete()
    SxQcRequest.objects.filter(code=DEMO_QC).delete()
    SxQcInspection.objects.filter(code=DEMO_PKT).delete()
    SxFgReceiptRequest.objects.filter(code=DEMO_FG).delete()


@transaction.atomic
def run():
    ensure_progress_work_centers()
    _wipe()

    today = timezone.localdate()
    User = get_user_model()
    operator = (
        User.objects.filter(is_active=True, is_superuser=True).order_by("id").first()
        or User.objects.filter(is_active=True).order_by("id").first()
    )

    doc = ProductTechDoc.objects.filter(product_code=STYLE).first()
    product_name = (doc.product_name if doc else "") or "QA bong da Just Play Raider xanh bich"
    bom = (
        BomVersion.objects.filter(tech_doc__product_code=STYLE)
        .order_by("-id")
        .first()
    )
    total = sum((q for _, q in SIZE_QTY), Decimal("0"))
    size_qtys = {s: int(q) for s, q in SIZE_QTY}

    so = SxSalesOrder.objects.create(
        code=DEMO_SO,
        customer_name="CLB demo — Raider xanh bich",
        request_date=today - timedelta(days=7),
        due_date=today + timedelta(days=5),
        confirm_status=SxSalesOrder.CONFIRM_CONFIRMED,
        confirmed_by=operator,
        confirmed_at=timezone.now(),
        plan_status=SxSalesOrder.PLAN_IN_PROGRESS,
        plan_priority=SxSalesOrder.PRIORITY_URGENT,
        plan_rank=1,
        plan_queued_at=timezone.now() - timedelta(days=6),
        notes=DEMO_NOTE,
        is_demo=False,
        created_by=operator,
    )
    SxSalesOrderLine.objects.create(
        order=so,
        product_code=STYLE,
        product_name=product_name,
        qty=total,
        size_qtys=size_qtys,
        bom_version=bom,
        routing=bom.routing if bom else None,
        sort_order=10,
    )
    seed_order_plan_steps_from_template(so)

    mo = SxProductionOrder.objects.create(
        code=DEMO_MO,
        product_code=STYLE,
        product_name=product_name,
        qty=total,
        order_date=today - timedelta(days=6),
        due_date=today + timedelta(days=5),
        planned_start=today - timedelta(days=6),
        planned_end=today + timedelta(days=5),
        status=SxProductionOrder.STATUS_IN_PROGRESS,
        sales_order=so,
        bom_version=bom,
        routing=bom.routing if bom else None,
        notes=DEMO_NOTE,
        is_demo=False,
        created_by=operator,
    )
    for size, qty in SIZE_QTY:
        SxProductionOrderLine.objects.create(
            production_order=mo,
            size_label=size,
            color_label="xanh bich",
            color_code="",
            qty=qty,
            sku_code=f"{STYLE}-{size}",
        )

    steps = progress_steps()
    for sd in steps:
        ensure_mo_step_for_template(mo=mo, step_def=sd)
    SxMoProcessStep.objects.filter(production_order=mo).update(
        status=SxMoProcessStep.STATUS_DONE,
    )

    stats = []
    n = 0
    for sd in steps:
        for size, qty in SIZE_QTY:
            n += 1
            stats.append(
                SxProductionStat(
                    code=f"TKSX-F001-{n:04d}",
                    production_order=mo,
                    stat_date=today - timedelta(days=1 if sd.group != "GIAO_HANG" else 0),
                    process_name=sd.label,
                    qty_good=qty,
                    qty_defect=Decimal("0"),
                    team_label=sd.group,
                    size_label=size,
                    sku_code=f"{STYLE}-{size}",
                    color_label="xanh bich",
                    color_code="",
                    status=SxProductionStat.STATUS_CONFIRMED,
                    notes="FULL seed — tat ca cong doan",
                    is_demo=False,
                )
            )
    SxProductionStat.objects.bulk_create(stats)
    _recompute_mo_progress(mo)
    mo.refresh_from_db()
    if mo.status == SxProductionOrder.STATUS_DONE:
        mo.status = SxProductionOrder.STATUS_IN_PROGRESS
        mo.save(update_fields=["status"])

    qc = SxQcRequest.objects.create(
        code=DEMO_QC,
        production_order=mo,
        product_code=STYLE,
        product_name=product_name,
        stage_name="Giao hang thanh pham",
        qty=total,
        request_date=today,
        status="done",
        notes=DEMO_NOTE,
        is_demo=False,
        created_by=operator,
    )
    SxQcInspection.objects.create(
        code=DEMO_PKT,
        qc_request=qc,
        inspected_at=today,
        qty_sample=total,
        qty_pass=total,
        qty_fail=Decimal("0"),
        result=SxQcInspection.RESULT_PASS,
        status="done",
        notes=DEMO_NOTE,
        is_demo=False,
        created_by=operator,
    )

    for slug, _gk, _mk, _label in TEAM_SLUGS:
        close_team_job(mo_id=mo.pk, team_slug=slug, user=operator, notes=DEMO_NOTE)

    prefill = fg_receipt_prefill(mo=mo)
    branch = KvBranch.objects.filter(branch_name__icontains="Xuong").first()
    if branch is None:
        branch = KvBranch.objects.order_by("id").first()
    wh_code = f"kv:{branch.pk}" if branch else ""
    wh_name = (branch.branch_name if branch else "") or ""

    fg = create_fg_receipt_from_mo(
        production_order_id=mo.pk,
        qty=total,
        code=DEMO_FG,
        notes=DEMO_NOTE,
        request_date=today,
        lines=prefill.get("lines") or [],
        received_by=operator,
        warehouse_code=wh_code,
        warehouse_name=wh_name,
    )

    print("SEED_OK")
    print("so", so.pk, so.code, so.plan_priority, "due", so.due_date)
    print("mo", mo.pk, mo.code, mo.status, "qty", mo.qty, "qty_done", mo.qty_done)
    print("steps", mo.mo_process_steps.count(), "stats", mo.production_stats.count())
    print("qc", qc.pk, qc.code)
    print("fg", fg.pk, fg.code, fg.status, "qty", fg.qty, "lines", fg.lines.count(), "wh", fg.warehouse_name)
    print("urls")
    print(f"  don hang: https://portal.justplay.vn/san-xuat/don-hang/{so.pk}/")
    print(f"  lenh sx:  https://portal.justplay.vn/san-xuat/dieu-phoi/lenh-sx/{mo.pk}/")
    print(f"  tien do:  https://portal.justplay.vn/san-xuat/cong-viec-to/tien-do-hang-hoa/")
    print(f"  ycntp:    https://portal.justplay.vn/san-xuat/dieu-phoi/yeu-cau-nhap-tp/{fg.pk}/")


run()
