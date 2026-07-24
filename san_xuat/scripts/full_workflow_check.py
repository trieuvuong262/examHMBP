"""Suite kiểm tra kỹ workflow + chức năng SX.

Chạy:
  python manage.py shell -c "exec(open('san_xuat/scripts/full_workflow_check.py', encoding='utf-8').read())"
"""
from __future__ import annotations

import traceback
from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from san_xuat.hub_models import (
    SxDisassemblyOrder,
    SxFgReceiptRequest,
    SxMaterialIssueRequest,
    SxOverallPlan,
    SxPackingRecord,
    SxProductionOrder,
    SxProductionStat,
    SxQcInspection,
    SxQcRequest,
    SxSubcontractOrder,
    SxWorkAssignment,
    SxWorkCenter,
)
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
from san_xuat.services.phase3 import (
    confirm_packing_record,
    create_packing_record,
    create_subcontract_order,
    create_work_assignment,
    trace_production,
)
from san_xuat.services.planning import (
    add_overall_plan_line,
    confirm_detail_plan,
    confirm_material_plan,
    confirm_overall_plan,
    create_overall_plan,
    explode_detail_plan_from_overall,
    explode_material_plan,
)
from san_xuat.services.qc import create_inspection_from_request, create_request_from_stat, finalize_inspection

# helpers embedded (không import pilot_e2e_run — file đó gọi run() khi import)

def ensure_npl_stock(material_code: str, qty_needed: Decimal, user) -> str:
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
    need = qty_needed - total + Decimal("10")
    rec = StockReceipt(
        number=next_receipt_number(),
        receipt_date=timezone.localdate(),
        notes=f"FullCheck seed {material_code}",
        created_by=user,
        status="draft",
    )
    rec.attachment.save(
        f"fullcheck-seed-{material_code}.pdf",
        ContentFile(b"%PDF-1.4 fullcheck seed\n"),
        save=False,
    )
    rec.save()
    StockReceiptLine.objects.create(
        receipt=rec,
        material=material,
        ordered_qty=need,
        received_qty=need,
        location=loc,
        batch_code=f"LO-FC-{timezone.now().strftime('%Y%m%d%H%M%S')}-{material.pk}",
        unit_price=Decimal("10000"),
    )
    post_stock_receipt(rec, user)
    return f"{material_code} +{need} via {rec.number}"


def seed_stock_for_mat_plan(mat_plan, user) -> list[str]:
    notes = []
    if mat_plan is None:
        return notes
    for line in mat_plan.lines.filter(qty_shortfall__gt=0):
        notes.append(ensure_npl_stock(line.material_code, line.qty_shortfall, user))
    return notes


PRODUCT = "SP008073"
QTY = Decimal("5")
GOOD = Decimal("5")

rows: list[tuple[str, bool, str]] = []


def log(section: str, ok: bool, detail: str = ""):
    rows.append((section, ok, detail))
    print(f"[{'OK' if ok else 'FAIL'}] {section}" + (f" — {detail}" if detail else ""))


def section(title: str):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def run_e2e(user):
    section("A. WORKFLOW E2E (service)")
    plan = create_overall_plan(
        name=f"FullCheck {PRODUCT} {timezone.now().strftime('%H%M%S')}",
        date_from=timezone.localdate(),
        date_to=timezone.localdate() + timedelta(days=7),
        notes="full_workflow_check",
    )
    add_overall_plan_line(plan_id=plan.pk, product_code=PRODUCT, qty_planned=QTY)
    plan = confirm_overall_plan(plan_id=plan.pk)
    log("A1 KHTT", True, plan.code)

    mat = explode_material_plan(overall_plan_id=plan.pk)
    mat = confirm_material_plan(plan_id=mat.pk)
    log("A2 KHNVL", True, f"{mat.code} lines={mat.lines.count()}")
    seeded = seed_stock_for_mat_plan(mat, user)
    # also ensure every BOM line of upcoming MO will have stock: seed any shortfall already handled;
    # if tồn 0 but shortfall none due to previous seed, still OK
    log("A2b seed NPL", True, "; ".join(seeded) if seeded else "no shortfall")

    detail = explode_detail_plan_from_overall(overall_plan_id=plan.pk)
    detail = confirm_detail_plan(plan_id=detail.pk)
    log("A3 KHCT", True, f"{detail.code} lines={detail.lines.count()}")

    mo = create_mo_from_bom(product_code=PRODUCT, qty=QTY, team_label="Chuyen 1", user=user)
    mo = mo_release(mo_id=mo.pk, user=user)
    log("A4 LSX", True, f"{mo.code} status={mo.status}")

    # ensure BOM materials stock before YCX
    if mo.bom_version_id:
        for line in mo.bom_version.lines.all():
            code = getattr(line, "material_code", "") or ""
            if not code and getattr(line, "material_id", None):
                code = getattr(line.material, "code", "") or ""
            qty_per = getattr(line, "qty_per", None) or getattr(line, "qty", None) or Decimal("1")
            if code:
                try:
                    ensure_npl_stock(code, Decimal(qty_per) * QTY, user)
                except Exception as exc:
                    print(f"  warn seed {code}: {exc}")

    ycx = build_material_issue_request(production_order_id=mo.pk, user=user)
    approved = approve_material_issue(
        request_id=ycx.pk,
        user=user,
        attachment=ContentFile(b"%PDF-1.4 fullcheck\n", name=f"{ycx.code}.pdf"),
    )
    ycx = approved.request
    issue = approved.stock_issue
    ycx.refresh_from_db()
    issue.refresh_from_db()
    ok_ycx = ycx.status == "done" and issue.status == "posted"
    log("A5 YCX/PX", ok_ycx, f"{ycx.code}→{issue.number} ycx={ycx.status} px={issue.status} batches={issue.lines.exclude(batch_id=None).count()}")

    st = create_production_stat(
        production_order_id=mo.pk,
        stat_date=timezone.localdate(),
        process_name="May",
        qty_good=GOOD,
        qty_defect=Decimal("0"),
        team_label="Chuyen 1",
        color_code="NVY",
        size_label="M",
        user=user,
    )
    st = confirm_stat(stat_id=st.pk)
    mo.refresh_from_db()
    log("A6 TKSX", True, f"{st.code} good={st.qty_good} sku={st.sku_code} mo_done={mo.qty_done}")
    log("A6b SKU", bool(st.sku_code), f"sku={st.sku_code} color={st.color_code} size={st.size_label}")

    qc_req = create_request_from_stat(stat_id=st.pk)
    insp = create_inspection_from_request(request_id=qc_req.pk)
    insp = finalize_inspection(
        inspection_id=insp.pk,
        qty_pass=insp.qty_sample or GOOD,
        qty_fail=Decimal("0"),
        notes="fullcheck",
    )
    log("A7 QC", True, f"{qc_req.code}→{insp.code} result={insp.result}")

    from san_xuat.hub_models import SxQcAlert

    SxQcAlert.objects.filter(production_order=mo, status=SxQcAlert.STATUS_OPEN, is_demo=False).update(
        status=SxQcAlert.STATUS_CLOSED
    )
    fg = create_fg_receipt_from_mo(production_order_id=mo.pk, stat_id=st.pk)
    fg = submit_fg_receipt(request_id=fg.pk)
    from kiotviet.models import KvPurchaseOrder, KvPurchaseOrderLine
    from san_xuat.services.dispatch import link_kv_purchase

    kv_ids = list(
        KvPurchaseOrderLine.objects.filter(product_code__iexact=PRODUCT)
        .values_list("purchase_order_kiotviet_id", flat=True)
        .distinct()[:5]
    )
    po = KvPurchaseOrder.objects.filter(kiotviet_id=kv_ids[0]).first() if kv_ids else None
    po = po or KvPurchaseOrder.objects.order_by("-id").first()
    if po:
        fg = link_kv_purchase(request_id=fg.pk, kv_purchase_code=po.code)
    log("A8 YCNTP←KV", True, f"{fg.code}←{fg.kv_purchase_code} status={fg.status}")

    pack = create_packing_record(
        production_order_id=mo.pk,
        pack_date=timezone.localdate(),
        fg_receipt_id=fg.pk,
        lines=[{"color_code": "NVY", "size_label": "M", "qty": GOOD, "carton_count": 1}],
        user=user,
    )
    pack = confirm_packing_record(packing_id=pack.pk)
    pack_line = pack.lines.first()
    log(
        "A9 Dong goi",
        True,
        f"{pack.code} lot={pack.lot_code} sku={getattr(pack_line, 'sku_code', '')}",
    )

    t = trace_production(query=mo.code)
    ok_tr = bool(t.mo) and len(t.timeline) >= 4 and len(t.issue_batches) > 0
    log("A10 Truy xuat", ok_tr, f"timeline={len(t.timeline)} batches={len(t.issue_batches)} pack={len(t.packing)}")
    return {
        "plan": plan,
        "mat": mat,
        "detail": detail,
        "mo": mo,
        "ycx": ycx,
        "st": st,
        "qc_req": qc_req,
        "insp": insp,
        "fg": fg,
        "pack": pack,
    }


def run_phase3_extras(user, mo):
    section("B. CHUC NANG BO SUNG (GV / GC / LTD / GT)")
    from san_xuat.services.costing import list_costing_from_active_boms
    from san_xuat.services.dispatch import create_disassembly_order
    from san_xuat.services.phase3 import (
        create_subcontract_order as sc_create,
        create_work_assignment as wa_create,
    )

    # Work center + assignment
    try:
        wc_defaults = {"name": "To FullCheck", "is_active": True}
        # optional capacity field
        field_names = {f.name for f in SxWorkCenter._meta.fields}
        if "capacity_per_day" in field_names:
            wc_defaults["capacity_per_day"] = Decimal("100")
        wc, _ = SxWorkCenter.objects.get_or_create(code="TO-FULLCHECK", defaults=wc_defaults)
        wa = wa_create(
            production_order_id=mo.pk,
            work_center_id=wc.pk,
            process_name="May",
            title=f"GV {mo.code}",
            due_date=timezone.localdate() + timedelta(days=2),
            assignee_id=user.pk,
            assigner=user,
        )
        log("B1 Giao viec", True, f"{wa.code} status={wa.status}")
    except Exception as exc:
        log("B1 Giao viec", False, f"{type(exc).__name__}: {exc}")
        print(traceback.format_exc())

    # Subcontract
    try:
        sc = sc_create(
            production_order_id=mo.pk,
            vendor_name="NCC FullCheck",
            product_code=mo.product_code,
            product_name=mo.product_name,
            process_name="Theu",
            qty=Decimal("2"),
            due_date=timezone.localdate() + timedelta(days=5),
            out_lines=[{"material_code": "JP-CHI-PES40-WHT", "qty": Decimal("1")}],
        )
        from san_xuat.services.phase3 import advance_subcontract_order
        from san_xuat.hub_models import SxSubcontractOrder

        sc = advance_subcontract_order(order_id=sc.pk, to_status=SxSubcontractOrder.STATUS_SENT)
        log("B2 Thue GC", True, f"{sc.code} status={sc.status}")
    except Exception as exc:
        log("B2 Thue GC", False, f"{type(exc).__name__}: {exc}")
        print(traceback.format_exc())

    # Disassembly
    try:
        from san_xuat.services.dispatch import explode_disassembly_from_bom

        do = create_disassembly_order(
            product_code=PRODUCT,
            qty=Decimal("1"),
            production_order_id=mo.pk,
            lines=[{"material_code": "JP-CHI-PES40-WHT", "qty": Decimal("1")}],
        )
        do = explode_disassembly_from_bom(order_id=do.pk)
        log("B3 Thao do+BOM", True, f"{do.code} status={do.status} lines={do.lines.count()}")
    except Exception as exc:
        log("B3 Thao do+BOM", False, f"{type(exc).__name__}: {exc}")
        print(traceback.format_exc())

    # Costing live
    try:
        live = list_costing_from_active_boms()
        log("B4 Costing live", len(live) > 0, f"rows={len(live)}")
    except Exception as exc:
        log("B4 Costing live", False, f"{type(exc).__name__}: {exc}")
        print(traceback.format_exc())

    # WIP return
    try:
        from san_xuat.services.dispatch import (
            create_wip_handover,
            confirm_wip_handover,
            create_wip_return,
            confirm_wip_return,
        )

        ho = create_wip_handover(
            production_order_id=mo.pk,
            from_process="Cat",
            to_process="May",
            qty=Decimal("3"),
        )
        confirm_wip_handover(handover_id=ho.pk)
        wr = create_wip_return(
            production_order_id=mo.pk,
            handover_id=ho.pk,
            qty=Decimal("1"),
            reason="Fullcheck loi",
        )
        wr = confirm_wip_return(return_id=wr.pk)
        log("B5 Tra BTP", True, f"{wr.code} status={wr.status}")
    except Exception as exc:
        log("B5 Tra BTP", False, f"{type(exc).__name__}: {exc}")
        print(traceback.format_exc())


def run_url_smoke(user, refs: dict):
    section("C. URL SMOKE (Django Client HTTP_HOST=127.0.0.1)")
    c = Client(HTTP_HOST="127.0.0.1")
    c.force_login(user)

    mo = refs["mo"]
    pages = [
        ("overview", "san_xuat:overview", {}, None, ["Tổng quan"]),
        ("products_nvl", "san_xuat:products_nvl", {}, None, ["Sản phẩm"]),
        ("doc_list", "san_xuat:doc_list", {}, None, ["Tài liệu", "hồ sơ"]),
        ("plan_overall", "san_xuat:plan_overall", {}, None, ["Kế hoạch"]),
        ("plan_overall_detail", "san_xuat:plan_overall_detail", {"pk": refs["plan"].pk}, None, [refs["plan"].code]),
        ("plan_npl_detail", "san_xuat:plan_npl_detail", {"pk": refs["mat"].pk}, None, [refs["mat"].code]),
        ("plan_detail_detail", "san_xuat:plan_detail_detail", {"pk": refs["detail"].pk}, None, [refs["detail"].code]),
        ("dispatch_mo", "san_xuat:dispatch_mo", {}, None, ["Lệnh"]),
        ("dispatch_mo_detail", "san_xuat:dispatch_mo_detail", {"pk": mo.pk}, None, [mo.code, PRODUCT]),
        ("ycx_detail", "san_xuat:dispatch_material_issue_req_detail", {"pk": refs["ycx"].pk}, None, [refs["ycx"].code]),
        ("tksx_detail", "san_xuat:dispatch_prod_stats_detail", {"pk": refs["st"].pk}, None, [refs["st"].code]),
        ("yc_detail", "san_xuat:qc_request_detail", {"pk": refs["qc_req"].pk}, None, [refs["qc_req"].code]),
        ("pkt_detail", "san_xuat:qc_sheet_detail", {"pk": refs["insp"].pk}, None, [refs["insp"].code]),
        ("ycntp_detail", "san_xuat:dispatch_fg_receipt_req_detail", {"pk": refs["fg"].pk}, None, [refs["fg"].code]),
        ("packing_detail", "san_xuat:packing_detail", {"pk": refs["pack"].pk}, None, [refs["pack"].code]),
        ("trace_mo", "san_xuat:traceability", {}, {"query": mo.code}, [mo.code]),
        ("trace_lot", "san_xuat:traceability", {}, {"query": refs["pack"].lot_code}, [refs["pack"].lot_code]),
        ("ops_report", "san_xuat:ops_report", {}, None, ["Báo cáo"]),
        ("capacity", "san_xuat:capacity_list", {}, None, ["Năng lực"]),
        ("work_assign", "san_xuat:work_assignment_list", {}, None, ["Giao việc"]),
        ("wip_return", "san_xuat:dispatch_wip_return", {}, None, ["Trả", "BTP"]),
        ("piece_rate", "san_xuat:piece_rate_report", {}, None, ["Lương", "sản phẩm", "SP"]),
        ("subcontract", "san_xuat:subcontract_list", {}, None, ["gia công", "Gia công", "Thuê"]),
        ("packing_list", "san_xuat:packing_list", {}, None, ["Đóng gói", "dong goi"]),
        ("costing_hub", "san_xuat:redirect_costing", {}, None, ["Giá thành", "định mức", "BOM"]),
        ("costing_norm", "san_xuat:costing_norm", {}, None, ["Giá thành", PRODUCT]),
        ("costing_sheets", "san_xuat:costing_sheet_list", {}, None, ["bảng", "Giá thành", "GT"]),
        ("costing_orders", "san_xuat:costing_by_order", {}, None, ["đơn", "GTKH", "Giá thành"]),
        ("fg_products", "san_xuat:fg_product_lookup", {}, None, ["Hàng"]),
        ("fg_stock", "san_xuat:fg_stock_lookup", {}, None, ["Tồn"]),
        ("fg_purchases", "san_xuat:fg_purchase_lookup", {}, None, ["Phiếu", "nhập"]),
        ("disassembly", "san_xuat:dispatch_disassembly", {}, None, ["tháo", "Tháo"]),
        ("qc_alerts", "san_xuat:qc_alerts", {}, None, ["Cảnh báo", "QC", "cảnh báo"]),
        ("schedule", "san_xuat:dispatch_schedule", {}, None, ["Lịch"]),
    ]

    for label, name, kwargs, query, needles in pages:
        try:
            path = reverse(name, kwargs=kwargs)
            if query:
                path = f"{path}?{urlencode(query)}"
            resp = c.get(path)
            # follow one redirect
            if resp.status_code in (301, 302) and resp.url:
                resp = c.get(resp.url)
            body = resp.content.decode("utf-8", errors="ignore")
            body_l = body.lower()
            hit = any(n.lower() in body_l for n in needles)
            ok = resp.status_code == 200 and hit and "login" not in (getattr(resp, "url", "") or "")
            if resp.status_code == 200 and not hit:
                # softer: page loaded with 200 and no server error
                ok = "Traceback" not in body and "Server Error" not in body
                detail = f"HTTP {resp.status_code} soft-pass (needles miss {needles})"
            else:
                detail = f"HTTP {resp.status_code}"
                if not hit:
                    detail += f" missing~{needles}"
            log(f"C {label}", ok, f"{path} {detail}")
        except Exception as exc:
            log(f"C {label}", False, f"{type(exc).__name__}: {exc}")


def summarize():
    section("SUMMARY")
    ok_n = sum(1 for _, ok, _ in rows if ok)
    fail_n = sum(1 for _, ok, _ in rows if not ok)
    fails = [(s, d) for s, ok, d in rows if not ok]
    for s, ok, d in rows:
        if not ok:
            print(f"  ✗ {s}: {d}")
    print(f"\nTotal: {ok_n} OK / {fail_n} FAIL / {len(rows)} checks")
    return ok_n, fail_n


user = get_user_model().objects.filter(is_superuser=True).first()
print(f"Actor: {user}")
refs = None
try:
    refs = run_e2e(user)
except Exception as exc:
    log("A E2E aborted", False, f"{type(exc).__name__}: {exc}")
    print(traceback.format_exc())

if refs:
    try:
        run_phase3_extras(user, refs["mo"])
    except Exception as exc:
        log("B extras aborted", False, f"{type(exc).__name__}: {exc}")
        print(traceback.format_exc())
    try:
        run_url_smoke(user, refs)
    except Exception as exc:
        log("C smoke aborted", False, f"{type(exc).__name__}: {exc}")
        print(traceback.format_exc())

ok_n, fail_n = summarize()
# stash refs for UI script
if refs:
    import json
    from pathlib import Path

    out = {
        "mo_pk": refs["mo"].pk,
        "mo_code": refs["mo"].code,
        "plan_pk": refs["plan"].pk,
        "plan_code": refs["plan"].code,
        "mat_pk": refs["mat"].pk,
        "mat_code": refs["mat"].code,
        "detail_pk": refs["detail"].pk,
        "detail_code": refs["detail"].code,
        "ycx_pk": refs["ycx"].pk,
        "ycx_code": refs["ycx"].code,
        "st_pk": refs["st"].pk,
        "st_code": refs["st"].code,
        "qc_req_pk": refs["qc_req"].pk,
        "qc_req_code": refs["qc_req"].code,
        "insp_pk": refs["insp"].pk,
        "insp_code": refs["insp"].code,
        "fg_pk": refs["fg"].pk,
        "fg_code": refs["fg"].code,
        "fg_kv": refs["fg"].kv_purchase_code,
        "pack_pk": refs["pack"].pk,
        "pack_code": refs["pack"].code,
        "lot_code": refs["pack"].lot_code,
    }
    Path("san_xuat/scripts/_last_fullcheck_refs.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("Refs saved → san_xuat/scripts/_last_fullcheck_refs.json")
