"""Test nhắc đẩy đặt cơm trên Chrome + Edge (Playwright)."""
from __future__ import annotations

import re
import sys
import time

from playwright.sync_api import sync_playwright

BASE = 'https://portal.justplay.vn'
USER = 'admin'
PASS = '123123sS@@'
BROWSERS = (
    ('chrome', 'chromium', {'channel': 'chrome'}),
    ('edge', 'chromium', {'channel': 'msedge'}),
)


def login(page):
    page.goto(f'{BASE}/accounts/login/', wait_until='domcontentloaded')
    page.fill('input[name="username"]', USER)
    page.fill('input[name="password"]', PASS)
    page.click('button[type="submit"]')
    page.wait_for_url(f'{BASE}/**', timeout=30000)


def run_browser(label: str, browser_type: str, launch_kwargs: dict) -> dict:
    result = {
        'browser': label,
        'push_ui': False,
        'subscribed': False,
        'test_ok': False,
        'error': '',
    }
    with sync_playwright() as p:
        browser = getattr(p, browser_type).launch(headless=True, **launch_kwargs)
        context = browser.new_context()
        context.grant_permissions(['notifications'])
        page = context.new_page()

        def on_dialog(dialog):
            dialog.accept()

        page.on('dialog', on_dialog)

        try:
            login(page)
            page.goto(f'{BASE}/', wait_until='networkidle', timeout=60000)

            enable = page.locator('#jpMealPushEnable')
            test_btn = page.locator('#jpMealPushTest')
            success = page.locator('#jpMealPushSuccess')

            result['push_ui'] = enable.count() > 0 or test_btn.count() > 0

            if enable.is_visible():
                enable.click()
                page.wait_for_timeout(3000)

            if success.is_hidden():
                page.wait_for_selector('#jpMealPushSuccess', state='visible', timeout=15000)
            result['subscribed'] = success.is_visible()

            if test_btn.is_visible():
                with page.expect_response(lambda r: '/tien-ich/push/test/' in r.url) as resp_info:
                    test_btn.click()
                resp = resp_info.value
                body = resp.json()
                result['test_ok'] = resp.ok and body.get('ok')
                if not result['test_ok']:
                    result['error'] = body.get('message') or resp.status_text
            else:
                result['error'] = 'Không thấy nút Gửi thử'
        except Exception as exc:
            result['error'] = str(exc)[:300]
        finally:
            browser.close()
    return result


def main():
    results = []
    for label, btype, kwargs in BROWSERS:
        print(f'==> {label}')
        try:
            results.append(run_browser(label, btype, kwargs))
        except Exception as exc:
            results.append({'browser': label, 'error': str(exc)[:300]})
        time.sleep(1)

    print('\n=== RESULTS ===')
    ok = True
    for r in results:
        print(r)
        if not r.get('test_ok'):
            ok = False
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
