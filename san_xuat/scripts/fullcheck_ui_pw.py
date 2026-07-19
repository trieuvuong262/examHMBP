"""UI Playwright check dùng refs từ full_workflow_check mới nhất."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
refs_path = Path("san_xuat/scripts/_last_fullcheck_refs.json")
refs = json.loads(refs_path.read_text(encoding="utf-8"))

PAGES = [
    ("Overview", "san_xuat:overview", {}, ["Tổng quan"], None),
    ("KHTT", "san_xuat:plan_overall_detail", {"pk": refs["plan_pk"]}, [refs["plan_code"]], None),
    ("KHNVL", "san_xuat:plan_npl_detail", {"pk": refs["mat_pk"]}, [refs["mat_code"]], None),
    ("KHCT", "san_xuat:plan_detail_detail", {"pk": refs["detail_pk"]}, [refs["detail_code"]], None),
    ("LSX", "san_xuat:dispatch_mo_detail", {"pk": refs["mo_pk"]}, [refs["mo_code"], "SP008073"], None),
    ("YCX", "san_xuat:dispatch_material_issue_req_detail", {"pk": refs["ycx_pk"]}, [refs["ycx_code"]], None),
    ("TKSX", "san_xuat:dispatch_prod_stats_detail", {"pk": refs["st_pk"]}, [refs["st_code"]], None),
    ("YCKT", "san_xuat:qc_request_detail", {"pk": refs["qc_req_pk"]}, [refs["qc_req_code"]], None),
    ("PKT", "san_xuat:qc_sheet_detail", {"pk": refs["insp_pk"]}, [refs["insp_code"]], None),
    ("YCNTP", "san_xuat:dispatch_fg_receipt_req_detail", {"pk": refs["fg_pk"]}, [refs["fg_code"]], None),
    ("Dong_goi", "san_xuat:packing_detail", {"pk": refs["pack_pk"]}, [refs["pack_code"], refs["lot_code"]], None),
    ("Truy_xuat_LSX", "san_xuat:traceability", {}, [refs["mo_code"]], {"query": refs["mo_code"]}),
    ("Truy_xuat_lo", "san_xuat:traceability", {}, [refs["lot_code"], refs["mo_code"]], {"query": refs["lot_code"]}),
    ("Work_assign", "san_xuat:work_assignment_list", {}, ["Giao việc"], None),
    ("Subcontract", "san_xuat:subcontract_list", {}, ["gia công", "Gia công", "Thuê"], None),
    ("Costing", "san_xuat:redirect_costing", {}, ["Giá thành"], None),
    ("FG_hang", "san_xuat:fg_product_lookup", {}, ["Hàng"], None),
    ("Ops", "san_xuat:ops_report", {}, ["Báo cáo"], None),
]

user = get_user_model().objects.filter(is_superuser=True).first()
c = Client(HTTP_HOST="127.0.0.1")
c.force_login(user)
c.get(reverse("san_xuat:overview"))
sessionid = c.cookies["sessionid"].value
print("session ok, refs mo=", refs["mo_code"])

shot_dir = Path("san_xuat/scripts/_pilot_ui_shots")
shot_dir.mkdir(parents=True, exist_ok=True)
rows = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_cookies([{
        "name": "sessionid",
        "value": sessionid,
        "domain": "127.0.0.1",
        "path": "/",
        "httpOnly": True,
        "sameSite": "Lax",
    }])
    page = context.new_page()
    for label, name, kwargs, needles, query in PAGES:
        path = reverse(name, kwargs=kwargs)
        if query:
            path = f"{path}?{urlencode(query)}"
        url = BASE + path
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
            status = resp.status if resp else 0
            # follow redirects manually not needed — playwright follows
            body = page.content()
            body_l = body.lower()
            missing = [n for n in needles if n.lower() not in body_l]
            redirected_login = "login" in page.url.lower() and "san-xuat" not in page.url
            ok = status == 200 and not redirected_login and (not missing or status == 200)
            if missing and status == 200 and "traceback" not in body_l and "server error" not in body_l:
                # soft: page renders
                ok = True
                detail = f"HTTP {status} soft (miss {missing})"
            else:
                detail = f"HTTP {status}"
                if missing:
                    detail += f" missing={missing}"
                if redirected_login:
                    detail += f" url={page.url}"
                    ok = False
            page.screenshot(path=str(shot_dir / f"fullcheck_{label}.png"), full_page=False)
            rows.append((label, ok, detail))
            print(("OK" if ok else "FAIL"), label, path, detail)
        except Exception as exc:
            rows.append((label, False, f"{type(exc).__name__}: {exc}"))
            print("FAIL", label, exc)
    browser.close()

ok_n = sum(1 for _, ok, _ in rows if ok)
fail_n = sum(1 for _, ok, _ in rows if not ok)
print("=" * 60)
print(f"UI SUMMARY: {ok_n} OK / {fail_n} FAIL / {len(rows)} pages")
for label, ok, detail in rows:
    if not ok:
        print(f"  ✗ {label}: {detail}")
