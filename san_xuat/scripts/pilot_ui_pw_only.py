"""Playwright-only UI pilot (runserver must already be up on :8000)."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"

PAGES = [
    ("KHTT", "san_xuat:plan_overall_detail", {"pk": 5}, ["KHTT-2026-0003"]),
    ("KHNVL", "san_xuat:plan_npl_detail", {"pk": 3}, ["KHNVL-2026-0002"]),
    ("KHCT", "san_xuat:plan_detail_detail", {"pk": 3}, ["KHCT-2026-0002"]),
    ("LSX", "san_xuat:dispatch_mo_detail", {"pk": 10}, ["LSX-2026-0003", "SP008073"]),
    ("YCX", "san_xuat:dispatch_material_issue_req_detail", {"pk": 4}, ["YCX-2026-0003"]),
    ("TKSX", "san_xuat:dispatch_prod_stats_detail", {"pk": 5}, ["TKSX-2026-0004"]),
    ("YCKT", "san_xuat:qc_request_detail", {"pk": 4}, ["YCKT-2026-0003"]),
    ("PKT", "san_xuat:qc_sheet_detail", {"pk": 6}, ["PKT-2026-0005"]),
    ("YCNTP", "san_xuat:dispatch_fg_receipt_req_detail", {"pk": 3}, ["YCNTP-2026-0002", "PN002960"]),
    ("KV_PN", "san_xuat:fg_purchase_detail", {"purchase_id": 9072315}, ["PN002960"]),
    ("Dong_goi", "san_xuat:packing_detail", {"pk": 3}, ["DG-2026-0003", "LO-DG-2026-0003"]),
    ("Truy_xuat_LSX", "san_xuat:traceability", {}, ["LSX-2026-0003"], {"query": "LSX-2026-0003"}),
    ("Truy_xuat_KV", "san_xuat:traceability", {}, ["PN002960", "YCNTP-2026-0002"], {"query": "PN002960"}),
    ("Truy_xuat_lo", "san_xuat:traceability", {}, ["LO-DG-2026-0003", "LSX-2026-0003"], {"query": "LO-DG-2026-0003"}),
    ("Overview", "san_xuat:overview", {}, ["Tổng quan sản xuất"]),
]

user = get_user_model().objects.filter(is_superuser=True).first()
c = Client(HTTP_HOST="127.0.0.1")
c.force_login(user)
c.get(reverse("san_xuat:overview"))
sessionid = c.cookies["sessionid"].value
print("session", sessionid[:12], "…")

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
    for item in PAGES:
        label, name, kwargs, needles = item[0], item[1], item[2], item[3]
        query = item[4] if len(item) > 4 else None
        path = reverse(name, kwargs=kwargs)
        if query:
            path = f"{path}?{urlencode(query)}"
        url = BASE + path
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            status = resp.status if resp else 0
            body = page.content()
            missing = [n for n in needles if n not in body]
            redirected_login = "login" in page.url.lower() and "san-xuat" not in page.url
            ok = status == 200 and not missing and not redirected_login
            detail = f"HTTP {status}"
            if missing:
                detail += f" missing={missing}"
            if redirected_login:
                detail += f" url={page.url}"
                ok = False
            page.screenshot(path=str(shot_dir / f"{label}.png"))
            rows.append((label, ok, detail))
            print(("OK" if ok else "FAIL"), label, path, detail)
        except Exception as exc:
            rows.append((label, False, f"{type(exc).__name__}: {exc}"))
            print("FAIL", label, exc)
    browser.close()

ok_n = sum(1 for _, ok, _ in rows if ok)
fail_n = sum(1 for _, ok, _ in rows if not ok)
print("=" * 60)
print(f"Browser: {ok_n} OK / {fail_n} FAIL | shots={shot_dir}")
for label, ok, detail in rows:
    if not ok:
        print(" ✗", label, detail)
