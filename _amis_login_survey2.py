"""Login AMIS demo — wait longer, capture errors/tenant pick."""
from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

OUT = Path(r"d:\Project\PortalJustPlay\_amis_survey")
OUT.mkdir(parents=True, exist_ok=True)

EMAIL = "misademoava@gmail.com"
PASSWORD = "12345678@Bca"
TARGET = "https://demoamisapp.misa.vn/production/sale-order"


def shot(page, name: str) -> None:
    try:
        (OUT / f"{name}.txt").write_text(page.inner_text("body")[:60000], encoding="utf-8")
    except Exception:
        (OUT / f"{name}.txt").write_text("(no body text)", encoding="utf-8")
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)


def main() -> None:
    logs: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="vi-VN")
        page = context.new_page()
        page.set_default_timeout(60000)

        page.on("console", lambda m: logs.append(f"CONSOLE {m.type}: {m.text}"))
        page.on("pageerror", lambda e: logs.append(f"PAGEERROR {e}"))

        page.goto("https://demoamisapp.misa.vn/login/", wait_until="domcontentloaded")
        page.wait_for_selector('input[type="password"]', timeout=30000)
        time.sleep(1)

        # Fill by placeholder / role
        email = page.get_by_placeholder("Số điện thoại/email")
        if email.count() == 0:
            email = page.locator('input[type="text"], input[type="email"]').first
        pwd = page.locator('input[type="password"]').first
        email.click()
        email.fill("")
        email.fill(EMAIL)
        pwd.click()
        pwd.fill("")
        pwd.fill(PASSWORD)
        shot(page, "10_filled")

        page.get_by_role("button", name="Đăng nhập").click()
        logs.append("clicked login")

        # Wait up to 45s for either leave login or error toast
        deadline = time.time() + 45
        while time.time() < deadline:
            url = page.url
            body = ""
            try:
                body = page.inner_text("body")
            except Exception:
                pass
            low = body.lower()
            if "sale-order" in url or ("/login" not in url.lower() and "đăng nhập" not in low[:300]):
                logs.append(f"left_login url={url}")
                break
            if any(x in low for x in ["sai mật khẩu", "không đúng", "không tồn tại", "lỗi", "invalid", "incorrect"]):
                logs.append("error_detected")
                break
            if "đang xác thực" not in low and "login" in url.lower():
                # stuck after auth finished with message
                logs.append("auth_finished_still_login")
                break
            time.sleep(1)

        time.sleep(2)
        shot(page, "11_after_wait")
        logs.append(f"url_after={page.url}")

        # Company / app picker
        for label in [
            "Vào ứng dụng",
            "Tiếp tục",
            "AMIS Sản xuất",
            "Sản xuất",
            "Chọn công ty",
            "Xác nhận",
        ]:
            loc = page.get_by_text(label, exact=False).first
            try:
                if loc.count() and loc.is_visible():
                    loc.click(timeout=2000)
                    logs.append(f"clicked_text={label}")
                    time.sleep(2)
            except Exception as e:
                logs.append(f"skip {label}: {e}")

        shot(page, "12_after_picker")

        # Force navigate
        page.goto(TARGET, wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=30000)
        except PwTimeout:
            pass
        time.sleep(6)
        shot(page, "13_sale_order")
        logs.append(f"final={page.url} title={page.title()}")

        meta = {
            "url": page.url,
            "title": page.title(),
            "buttons": [t.strip() for t in page.locator("button").all_inner_texts() if t.strip()][:100],
            "ths": [t.strip() for t in page.locator("th").all_inner_texts() if t.strip()][:80],
            "nav": [t.strip() for t in page.locator("nav, .sidebar, [class*='menu']").all_inner_texts() if t.strip()][:30],
        }
        (OUT / "meta2.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT / "notes2.txt").write_text("\n".join(logs), encoding="utf-8")
        browser.close()
    print("DONE")
    print("\n".join(logs[-30:]))


if __name__ == "__main__":
    main()
