"""Pilot UI — mở các màn theo chứng từ E2E SP008073.

Chạy (cần runserver đang listen :8000, hoặc script tự start):
  python manage.py shell -c "exec(open('san_xuat/scripts/pilot_ui_browser.py', encoding='utf-8').read())"
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

BASE = "http://127.0.0.1:8000"

# PKs từ pilot E2E (SP008073)
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
    ("KV PN", "san_xuat:fg_purchase_detail", {"purchase_id": 9072315}, ["PN002960"]),
    ("Đóng gói", "san_xuat:packing_detail", {"pk": 3}, ["DG-2026-0003", "LO-DG-2026-0003"]),
    ("Truy xuất LSX", "san_xuat:traceability", {}, ["LSX-2026-0003"], {"query": "LSX-2026-0003"}),
    ("Truy xuất KV", "san_xuat:traceability", {}, ["PN002960", "YCNTP-2026-0002"], {"query": "PN002960"}),
    ("Truy xuất lô ĐG", "san_xuat:traceability", {}, ["LO-DG-2026-0003", "LSX-2026-0003"], {"query": "LO-DG-2026-0003"}),
            ("Overview", "san_xuat:overview", {}, ["Tổng quan sản xuất", "LSX"]),
]


def _server_up() -> bool:
    import urllib.request

    try:
        urllib.request.urlopen(BASE + "/", timeout=2)
        return True
    except Exception:
        return False


def ensure_server():
    if _server_up():
        print("runserver already up")
        return None
    print("starting runserver…")
    proc = subprocess.Popen(
        [sys.executable, "manage.py", "runserver", "127.0.0.1:8000"],
        cwd=str(Path(__file__).resolve().parents[2]),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        time.sleep(0.5)
        if _server_up():
            print("runserver ready")
            return proc
    raise RuntimeError("runserver failed to start")


def django_client_smoke() -> list[tuple[str, bool, str]]:
    """Smoke HTTP qua Django Client (force_login) — không cần browser."""
    user = get_user_model().objects.filter(is_superuser=True).first()
    client = Client(HTTP_HOST="127.0.0.1")
    client.force_login(user)
    rows = []
    for item in PAGES:
        label, name, kwargs, needles = item[0], item[1], item[2], item[3]
        query = item[4] if len(item) > 4 else None
        url = reverse(name, kwargs=kwargs)
        if query:
            from urllib.parse import urlencode

            url = f"{url}?{urlencode(query)}"
        resp = client.get(url)
        body = resp.content.decode("utf-8", errors="ignore")
        missing = [n for n in needles if n not in body]
        ok = resp.status_code == 200 and not missing
        detail = f"HTTP {resp.status_code}" + (f" missing={missing}" if missing else "")
        rows.append((label, ok, f"{url} — {detail}"))
        print(("OK" if ok else "FAIL"), label, detail)
    return rows


def playwright_smoke(sessionid: str) -> list[tuple[str, bool, str]]:
    from playwright.sync_api import sync_playwright

    rows = []
    shot_dir = Path("san_xuat/scripts/_pilot_ui_shots")
    shot_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        context.add_cookies([
            {
                "name": "sessionid",
                "value": sessionid,
                "domain": "127.0.0.1",
                "path": "/",
                "httpOnly": True,
                "sameSite": "Lax",
            },
        ])
        page = context.new_page()
        for item in PAGES:
            label, name, kwargs, needles = item[0], item[1], item[2], item[3]
            query = item[4] if len(item) > 4 else None
            path = reverse(name, kwargs=kwargs)
            if query:
                from urllib.parse import urlencode

                path = f"{path}?{urlencode(query)}"
            url = BASE + path
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=20000)
                status = resp.status if resp else 0
                body = page.content()
                missing = [n for n in needles if n not in body]
                # login redirect?
                redirected_login = "/accounts/login" in page.url or "/login" in page.url
                ok = status == 200 and not missing and not redirected_login
                detail = f"HTTP {status}" + (f" missing={missing}" if missing else "")
                if redirected_login:
                    detail += " (redirect login)"
                    ok = False
                page.screenshot(path=str(shot_dir / f"{label.replace(' ', '_')}.png"), full_page=False)
                rows.append((label, ok, f"{path} — {detail}"))
                print(("OK" if ok else "FAIL"), label, detail)
            except Exception as exc:
                rows.append((label, False, f"{path} — {type(exc).__name__}: {exc}"))
                print("FAIL", label, exc)
        browser.close()
    print(f"screenshots → {shot_dir}")
    return rows


def run():
    print("=" * 72)
    print("UI PILOT — Django Client")
    print("=" * 72)
    client_rows = django_client_smoke()

    print("\n" + "=" * 72)
    print("UI PILOT — Playwright browser")
    print("=" * 72)
    proc = ensure_server()
    try:
        user = get_user_model().objects.filter(is_superuser=True).first()
        c = Client(HTTP_HOST="127.0.0.1")
        c.force_login(user)
        # hit once so session is created
        c.get(reverse("san_xuat:overview"))
        sessionid = c.cookies["sessionid"].value
        browser_rows = playwright_smoke(sessionid)
    finally:
        if proc is not None:
            proc.terminate()

    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)
    for title, rows in [("Client", client_rows), ("Browser", browser_rows)]:
        ok_n = sum(1 for _, ok, _ in rows if ok)
        fail_n = sum(1 for _, ok, _ in rows if not ok)
        print(f"{title}: {ok_n} OK / {fail_n} FAIL")
        for label, ok, detail in rows:
            if not ok:
                print(f"  ✗ {label}: {detail}")


run()
