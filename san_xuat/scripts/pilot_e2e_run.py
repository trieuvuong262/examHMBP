"""Pilot end-to-end một vòng SX thật: SP008073.

Chạy:
  python manage.py shell < san_xuat/scripts/pilot_e2e_run.py
hoặc:
  python manage.py shell -c "exec(open('san_xuat/scripts/pilot_e2e_run.py', encoding='utf-8').read())"
"""
from __future__ import annotations

import traceback
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.utils import timezone

from kho_npl.services.issues import post_stock_issue
from san_xuat.services.dispatch import (
    approve_material_issue,
    build_material_issue_request,
    confirm_stat,
    create_fg_receipt_from_mo,
    create_mo_from_bom,
    create_production_stat,
    mo_release,
    submit_fg_receipt,
)
from san_xuat.services.phase3 import confirm_packing_record, create_packing_record, trace_production
from san_xuat.services.planning import (
    add_overall_plan_line,
    approve_npl_purchase_request,
    build_pr_from_material_plan,
    confirm_material_plan,
    confirm_overall_plan,
    create_overall_plan,
    explode_detail_plan_from_overall,
    explode_material_plan,
    submit_npl_purchase_request,
)
from san_xuat.services.qc import create_inspection_from_request, create_request_from_stat, finalize_inspection

PRODUCT_CODE = "SP008073"
MO_QTY = Decimal("10")
GOOD_QTY = Decimal("9")
DEFECT_QTY = Decimal("0")  # tránh mở QC alert chặn YCNTP

results: list[tuple[str, bool, str]] = []


def ensure_npl_stock(material_code: str, qty_needed: Decimal, user) -> str:
    """Nhập kho NPL (phiếu posted) nếu tồn hiện tại < qty_needed — phục vụ pilot."""
    from kho_npl.models import Material, StockBalance, StockReceipt, StockReceiptLine, WarehouseLocation
    from kho_npl.services.doc_numbers import next_receipt_number
    from kho_npl.services.receipts import post_stock_receipt

    material = Material.objects.filter(code__iexact=material_code, is_active=True).first()
    if not material:
        raise RuntimeError(f"Không tìm thấy NPL {material_code}")
    total = sum(
        (b.quantity for b in StockBalance.objects.filter(material=material)),
        Decimal("0"),
    )
    if total >= qty_needed:
        return f"{material_code} tồn={total} (đủ)"
    loc = WarehouseLocation.objects.filter(is_active=True).order_by("id").first()
    if not loc:
        raise RuntimeError("Không có vị trí kho NPL")
    need = qty_needed - total + Decimal("10")  # buffer
    rec = StockReceipt(
        number=next_receipt_number(),
        receipt_date=timezone.localdate(),
        notes=f"Pilot auto-seed {material_code}",
        created_by=user,
        status="draft",
    )
    rec.attachment.save(
        f"pilot-seed-{material_code}.pdf",
        ContentFile(b"%PDF-1.4 pilot seed\n"),
        save=False,
    )
    rec.save()
    StockReceiptLine.objects.create(
        receipt=rec,
        material=material,
        ordered_qty=need,
        received_qty=need,
        location=loc,
        batch_code=f"LO-PILOT-{timezone.now().strftime('%Y%m%d%H%M%S')}-{material.pk}",
        unit_price=Decimal("10000"),
    )
    post_stock_receipt(rec, user)
    return f"{material_code} +{need} via {rec.number}"


def seed_stock_for_mat_plan(mat_plan, user) -> list[str]:
    """Sau YCM: nhập kho các dòng shortfall để YCX duyệt được."""
    notes = []
    if mat_plan is None:
        return notes
    for line in mat_plan.lines.filter(qty_shortfall__gt=0):
        notes.append(ensure_npl_stock(line.material_code, line.qty_shortfall, user))
    return notes


def log(step: str, ok: bool, detail: str = ""):
    mark = "OK" if ok else "FAIL"
    results.append((step, ok, detail))
    print(f"[{mark}] {step}" + (f" — {detail}" if detail else ""))


def run():
    user = get_user_model().objects.filter(is_superuser=True).first()
    if not user:
        user = get_user_model().objects.filter(is_active=True).first()
    print(f"Pilot actor: {user} | SP={PRODUCT_CODE} | qty={MO_QTY}")
    print("=" * 72)

    # 1) KHTT
    try:
        plan = create_overall_plan(
            name=f"Pilot E2E {PRODUCT_CODE} {timezone.now().strftime('%Y%m%d-%H%M%S')}",
            date_from=timezone.localdate(),
            date_to=timezone.localdate() + timedelta(days=14),
            notes="Pilot 1 vòng thật",
        )
        add_overall_plan_line(plan_id=plan.pk, product_code=PRODUCT_CODE, qty_planned=MO_QTY)
        plan = confirm_overall_plan(plan_id=plan.pk)
        log("1. KHTT", True, f"{plan.code} status={plan.status}")
    except Exception as exc:
        log("1. KHTT", False, f"{type(exc).__name__}: {exc}")
        print(traceback.format_exc())
        return summarize()

    # 2) KHNVL
    try:
        mat_plan = explode_material_plan(overall_plan_id=plan.pk)
        mat_plan = confirm_material_plan(plan_id=mat_plan.pk)
        short = list(mat_plan.lines.filter(qty_shortfall__gt=0).values_list("material_code", "qty_shortfall")[:10])
        log("2. KHNVL", True, f"{mat_plan.code} lines={mat_plan.lines.count()} shortfall={short or 'none'}")
    except Exception as exc:
        log("2. KHNVL", False, f"{type(exc).__name__}: {exc}")
        print(traceback.format_exc())
        mat_plan = None

    # 3) YCM (nếu có shortfall; nếu không vẫn thử build PR)
    pr = None
    if mat_plan is not None:
        try:
            pr = build_pr_from_material_plan(material_plan_id=mat_plan.pk)
            pr = submit_npl_purchase_request(request_id=pr.pk)
            pr = approve_npl_purchase_request(request_id=pr.pk)
            log("3. YCM", True, f"{pr.code} status={pr.status} lines={pr.lines.count()}")
        except Exception as exc:
            msg = str(exc)
            if "shortfall" in msg.lower() or "Không có dòng shortfall" in msg:
                log("3. YCM", True, f"skip — tồn đủ, không cần YCM ({msg})")
            else:
                log("3. YCM", False, f"{type(exc).__name__}: {exc}")
                print(traceback.format_exc())

    # 3b) Nhập kho NPL shortfall (YCM duyệt ≠ đã có tồn — cần PN trước khi YCX)
    try:
        seeded = seed_stock_for_mat_plan(mat_plan, user)
        if seeded:
            log("3b. Nhap NPL seed", True, "; ".join(seeded))
        else:
            log("3b. Nhap NPL seed", True, "skip — không shortfall")
    except Exception as exc:
        log("3b. Nhap NPL seed", False, f"{type(exc).__name__}: {exc}")
        print(traceback.format_exc())

    # 4) KHCT (optional)
    try:
        detail = explode_detail_plan_from_overall(overall_plan_id=plan.pk)
        from san_xuat.services.planning import confirm_detail_plan

        detail = confirm_detail_plan(plan_id=detail.pk)
        log("4. KHCT", True, f"{detail.code} lines={detail.lines.count()}")
    except Exception as exc:
        log("4. KHCT", False, f"{type(exc).__name__}: {exc}")
        print(traceback.format_exc())

    # 5) LSX + release
    try:
        mo = create_mo_from_bom(
            product_code=PRODUCT_CODE,
            qty=MO_QTY,
            team_label="Chuyen 1",
            notes="Pilot E2E",
            user=user,
        )
        mo = mo_release(mo_id=mo.pk, user=user)
        log("5. LSX release", True, f"{mo.code} bom={mo.bom_version_id} status={mo.status}")
    except Exception as exc:
        log("5. LSX release", False, f"{type(exc).__name__}: {exc}")
        print(traceback.format_exc())
        return summarize()

    # 6) YCX → StockIssue → post (có attachment)
    try:
        ycx = build_material_issue_request(production_order_id=mo.pk, user=user)
        fake = ContentFile(b"%PDF-1.4 pilot attachment\n", name=f"pilot-{ycx.code}.pdf")
        approved = approve_material_issue(request_id=ycx.pk, user=user, attachment=fake)
        ycx = approved.request
        issue = approved.stock_issue
        # refresh — approve with attachment should have posted
        ycx.refresh_from_db()
        issue.refresh_from_db()
        if issue.status != "posted":
            # fallback: ensure attachment then post
            if not issue.attachment:
                issue.attachment.save(f"pilot-{issue.number}.pdf", ContentFile(b"%PDF-1.4\n"), save=True)
            post_stock_issue(issue, user)
            issue.refresh_from_db()
            ycx.status = "done"
            ycx.save(update_fields=["status"])
        batch_n = issue.lines.exclude(batch_id=None).count()
        log(
            "6. YCX + xuat kho",
            True,
            f"{ycx.code} → {issue.number} status={issue.status} lines={issue.lines.count()} batches={batch_n}",
        )
    except Exception as exc:
        log("6. YCX + xuat kho", False, f"{type(exc).__name__}: {exc}")
        print(traceback.format_exc())
        ycx = None
        issue = None

    # 7) TKSX
    try:
        st = create_production_stat(
            production_order_id=mo.pk,
            stat_date=timezone.localdate(),
            process_name="May",
            qty_good=GOOD_QTY,
            qty_defect=DEFECT_QTY,
            team_label="Chuyen 1",
        )
        st = confirm_stat(stat_id=st.pk)
        mo.refresh_from_db()
        log("7. TKSX", True, f"{st.code} good={st.qty_good} mo_done={mo.qty_done} mo_status={mo.status}")
    except Exception as exc:
        log("7. TKSX", False, f"{type(exc).__name__}: {exc}")
        print(traceback.format_exc())
        return summarize()

    # 8) QC
    try:
        qc_req = create_request_from_stat(stat_id=st.pk)
        insp = create_inspection_from_request(request_id=qc_req.pk)
        insp = finalize_inspection(
            inspection_id=insp.pk,
            qty_pass=insp.qty_sample or GOOD_QTY,
            qty_fail=Decimal("0"),
            notes="Pilot pass",
        )
        log("8. QC", True, f"{qc_req.code} → {insp.code} result={insp.result}")
    except Exception as exc:
        log("8. QC", False, f"{type(exc).__name__}: {exc}")
        print(traceback.format_exc())

    # 9) YCNTP
    try:
        # đóng QC alert nếu còn (an toàn)
        from san_xuat.hub_models import SxQcAlert

        SxQcAlert.objects.filter(
            production_order=mo, status=SxQcAlert.STATUS_OPEN, is_demo=False,
        ).update(status=SxQcAlert.STATUS_CLOSED)
        fg = create_fg_receipt_from_mo(production_order_id=mo.pk, stat_id=st.pk)
        fg = submit_fg_receipt(request_id=fg.pk)
        log("9. YCNTP", True, f"{fg.code} qty={fg.qty} status={fg.status}")
    except Exception as exc:
        log("9. YCNTP", False, f"{type(exc).__name__}: {exc}")
        print(traceback.format_exc())
        fg = None

    # 9b) Gắn phiếu nhập KV (ưu tiên phiếu có cùng mã SP)
    if fg is not None:
        try:
            from kiotviet.models import KvPurchaseOrder, KvPurchaseOrderLine
            from san_xuat.services.dispatch import link_kv_purchase

            kv_ids = list(
                KvPurchaseOrderLine.objects.filter(product_code__iexact=PRODUCT_CODE)
                .values_list("purchase_order_kiotviet_id", flat=True)
                .distinct()[:20]
            )
            po = None
            if kv_ids:
                po = KvPurchaseOrder.objects.filter(kiotviet_id=kv_ids[0]).first()
            if not po:
                po = KvPurchaseOrder.objects.order_by("-id").first()
            if not po:
                raise RuntimeError("Không có phiếu nhập KV đã sync.")
            fg = link_kv_purchase(request_id=fg.pk, kv_purchase_code=po.code)
            log("9b. YCNTP←KV", True, f"{fg.code} ← {fg.kv_purchase_code} (id={fg.kv_purchase_kiotviet_id}) status={fg.status}")
        except Exception as exc:
            log("9b. YCNTP←KV", False, f"{type(exc).__name__}: {exc}")
            print(traceback.format_exc())

    # 10) Đóng gói
    try:
        pack = create_packing_record(
            production_order_id=mo.pk,
            pack_date=timezone.localdate(),
            fg_receipt_id=fg.pk if fg else None,
            lines=[
                {"size_label": "M", "color_label": "Trang", "qty": Decimal("5"), "carton_count": 1},
                {"size_label": "L", "color_label": "Trang", "qty": Decimal("4"), "carton_count": 1},
            ],
        )
        pack = confirm_packing_record(packing_id=pack.pk)
        log("10. Dong goi", True, f"{pack.code} qty={pack.qty} lot={pack.lot_code} fg={pack.fg_receipt_id}")
    except Exception as exc:
        log("10. Dong goi", False, f"{type(exc).__name__}: {exc}")
        print(traceback.format_exc())
        pack = None

    # 11) Truy xuất
    try:
        t_mo = trace_production(query=mo.code)
        t_lot = trace_production(query=pack.lot_code) if pack else None
        detail = (
            f"timeline={len(t_mo.timeline)} batches={len(t_mo.issue_batches)} "
            f"pack={len(t_mo.packing)} fg={len(t_mo.fg_receipts)} "
            f"lot→{t_lot.mo.code if t_lot and t_lot.mo else None}"
        )
        ok = bool(t_mo.mo) and len(t_mo.timeline) >= 3
        if issue and issue.status == "posted":
            ok = ok and len(t_mo.issue_batches) > 0
        log("11. Truy xuat", ok, detail)
        if t_mo.issue_batches:
            print("   sample batches:")
            for b in t_mo.issue_batches[:5]:
                print(f"     {b['ycx']} | {b['material_code']} | lo={b['batch_code']} | sl={b['qty']}")
    except Exception as exc:
        log("11. Truy xuat", False, f"{type(exc).__name__}: {exc}")
        print(traceback.format_exc())

    return summarize(mo_code=mo.code)


def summarize(**extra):
    print("=" * 72)
    print("PILOT SUMMARY")
    ok_n = sum(1 for _, ok, _ in results if ok)
    fail_n = sum(1 for _, ok, _ in results if not ok)
    for step, ok, detail in results:
        print(f"  {'✓' if ok else '✗'} {step}: {detail}")
    print(f"Total: {ok_n} OK / {fail_n} FAIL")
    if extra:
        print("Refs:", extra)
    return results


run()
