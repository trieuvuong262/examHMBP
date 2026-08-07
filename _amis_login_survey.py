"""Login AMIS demo and capture sale-order page."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

OUT = Path(r"d:\Project\PortalJustPlay\_amis_survey")
OUT.mkdir(parents=True, exist_ok=True)

EMAIL = "misademoava@gmail.com"
PASSWORD = "12345678@Bca"
TARGET = "https://demoamisapp.misa.vn/production/sale-order"
LOGIN_CANDIDATES = [
    "https://demoamisapp.misa.vn/",
    "https://demoamisapp.misa.vn/login",
    "https://id.misa.vn/",
]


def dump_text(page, name: str) -> None:
    (OUT / f"{name}.txt").write_text(page.inner_text("body")[:50000], encoding="utf-8")
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)


def try_fill_login(page) -> bool:
    # Common MISA login selectors
    email_sels = [
        'input[type="email"]',
        'input[name="email"]',
        'input[name="username"]',
        'input[placeholder*="email" i]',
        'input[placeholder*="Email" i]',
        'input[placeholder*="tài khoản" i]',
        'input[placeholder*="Tài khoản" i]',
        '#email',
        '#username',
        'input.form-control[type="text"]',
    ]
    pass_sels = [
        'input[type="password"]',
        'input[name="password"]',
        '#password',
    ]
    email_el = None
    for s in email_sels:
        loc = page.locator(s).first
        if loc.count() and loc.is_visible():
            email_el = loc
            break
    pass_el = None
    for s in pass_sels:
        loc = page.locator(s).first
        if loc.count() and loc.is_visible():
            pass_el = loc
            break
    if not email_el or not pass_el:
        return False
    email_el.fill(EMAIL)
    pass_el.fill(PASSWORD)
    # submit
    for s in [
        'button[type="submit"]',
        'button:has-text("Đăng nhập")',
        'button:has-text("Login")',
        'button:has-text("Tiếp tục")',
        '.btn-login',
    ]:
        btn = page.locator(s).first
        if btn.count() and btn.is_visible():
            btn.click()
            return True
    pass_el.press("Enter")
    return True


def main() -> None:
    notes: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="vi-VN",
        )
        page = context.new_page()
        page.set_default_timeout(45000)

        page.goto(TARGET, wait_until="domcontentloaded")
        time.sleep(3)
        notes.append(f"start_url={page.url}")
        dump_text(page, "01_start")

        # If redirected to login / SSO
        for _ in range(3):
            url = page.url.lower()
            body = page.inner_text("body")[:2000]
            notes.append(f"url={page.url}")
            if "sale-order" in url and "đăng nhập" not in body.lower() and "login" not in body.lower()[:200]:
                # maybe already in
                if EMAIL.split("@")[0][:6] in body.lower() or "đơn" in body.lower():
                    break
            filled = try_fill_login(page)
            notes.append(f"filled_login={filled}")
            if filled:
                try:
                    page.wait_for_load_state("networkidle", timeout=20000)
                except PwTimeout:
                    pass
                time.sleep(4)
                dump_text(page, "02_after_login_attempt")
                # company/tenant select?
                for s in [
                    'button:has-text("Vào ứng dụng")',
                    'button:has-text("Tiếp tục")',
                    'button:has-text("Chọn")',
                    'text=AMIS Sản xuất',
                    'text=Sản xuất',
                ]:
                    loc = page.locator(s).first
                    if loc.count() and loc.is_visible():
                        try:
                            loc.click(timeout=3000)
                            time.sleep(2)
                            notes.append(f"clicked={s}")
                        except Exception as e:
                            notes.append(f"click_fail={s}:{e}")
                break
            # try id.misa
            page.goto(LOGIN_CANDIDATES[2], wait_until="domcontentloaded")
            time.sleep(2)
            dump_text(page, "01b_id_misa")

        # Navigate to sale-order again after login
        page.goto(TARGET, wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=25000)
        except PwTimeout:
            pass
        time.sleep(5)
        dump_text(page, "03_sale_order")
        notes.append(f"final_url={page.url}")

        # Extract table headers / menu / buttons
        meta = {
            "url": page.url,
            "title": page.title(),
            "buttons": [t.strip() for t in page.locator("button").all_inner_texts() if t.strip()][:80],
            "links": [t.strip() for t in page.locator("a").all_inner_texts() if t.strip()][:80],
            "ths": [t.strip() for t in page.locator("th").all_inner_texts() if t.strip()][:60],
            "tabs": [t.strip() for t in page.locator('[role="tab"], .tab, .nav-item').all_inner_texts() if t.strip()][:40],
        }
        (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "notes.txt").write_text("\n".join(notes), encoding="utf-8")

        # Try open first row detail
        row = page.locator("table tbody tr, .ms-table tbody tr, [class*='row']").first
        if row.count():
            try:
                row.click(timeout=3000)
                time.sleep(3)
                dump_text(page, "04_detail")
            except Exception as e:
                notes.append(f"row_click_fail={e}")

        context.close()
        browser.close()
    print("DONE", OUT)
    print("\n".join(notes))


if __name__ == "__main__":
    main()
