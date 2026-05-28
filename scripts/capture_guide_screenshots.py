#!/usr/bin/env python3
"""
Chụp màn hình portal.justplay.vn cho trang Hướng dẫn.

Usage:
  pip install playwright
  playwright install chromium

  # Chỉ trang đăng nhập (public):
  python scripts/capture_guide_screenshots.py

  # Đầy đủ (cần tài khoản portal):
  set GUIDE_CAPTURE_USER=your@justplay.vn
  set GUIDE_CAPTURE_PASSWORD=secret
  python scripts/capture_guide_screenshots.py

Env:
  GUIDE_BASE_URL   — mặc định https://portal.justplay.vn
  GUIDE_CAPTURE_USER / GUIDE_CAPTURE_PASSWORD — đăng nhập trước khi chụp
  GUIDE_OUTPUT_DIR — mặc định static/images/guide
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(os.environ.get('GUIDE_OUTPUT_DIR', ROOT / 'static' / 'images' / 'guide'))
BASE_URL = os.environ.get('GUIDE_BASE_URL', 'https://portal.justplay.vn').rstrip('/')
USER = os.environ.get('GUIDE_CAPTURE_USER', '')
PASSWORD = os.environ.get('GUIDE_CAPTURE_PASSWORD', '')
STAFF_USER = os.environ.get('GUIDE_CAPTURE_STAFF_USER', '')
STAFF_PASSWORD = os.environ.get('GUIDE_CAPTURE_STAFF_PASSWORD', '')

# (filename, path, mobile, wait_selector)
SHOTS_PUBLIC = [
    ('01-dang-nhap', '/accounts/login/', True, '.card-login'),
]

SHOTS_AUTH = [
    ('02-trang-chu', '/', False, '.portal-container'),
    ('02-trang-chu-mobile', '/', True, '.portal-container'),
    ('03-menu-mobile', '/', True, None),  # opens drawer via JS
    ('05-thong-bao', '/announcements/', False, '.jp-page'),
    ('06-bao-cao', '/reports/today/', False, '.jp-page'),
    ('07-dao-tao', '/training/my-courses/', False, '.jp-page'),
    ('08-kiem-tra', '/exams/', False, '.jp-page'),
    ('09-kpi', '/kpi/', False, '.jp-page'),
    ('04-doi-mat-khau', '/change-password/', False, '.change-password-container, .card-login, .jp-page'),
]

SHOTS_STAFF = [
    ('10-nhan-su', '/dashboard/users/', False, '.jp-hrm-page, .jp-page, table'),
]


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('Cần cài: pip install playwright && playwright install chromium', file=sys.stderr)
        sys.exit(1)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    print(f'Base URL: {BASE_URL}')
    print(f'Output:   {OUTPUT}')

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale='vi-VN',
            color_scheme='light',
            ignore_https_errors=True,
        )
        page = context.new_page()

        def capture(name: str, path: str, mobile: bool, wait_sel: str | None):
            vp = {'width': 390, 'height': 844} if mobile else {'width': 1280, 'height': 800}
            page.set_viewport_size(vp)
            url = BASE_URL + path
            print(f'  -> {name}.png  {url}')
            page.goto(url, wait_until='networkidle', timeout=60000)
            if wait_sel:
                for sel in wait_sel.split(', '):
                    try:
                        page.wait_for_selector(sel.strip(), timeout=15000)
                        break
                    except Exception:
                        continue
            page.wait_for_timeout(400)
            out = OUTPUT / f'{name}.png'
            page.screenshot(path=str(out), full_page=False)
            print(f'     saved {out.name} ({out.stat().st_size // 1024} KB)')

        print('\n[Public pages]')
        for item in SHOTS_PUBLIC:
            capture(*item)

        if USER and PASSWORD:
            print('\n[Login]')
            page.goto(BASE_URL + '/accounts/login/', wait_until='networkidle')
            page.fill('input[name="username"]', USER)
            page.fill('input[name="password"]', PASSWORD)
            page.click('button[type="submit"]')
            page.wait_for_load_state('networkidle')
            if '/login' in page.url or 'login' in page.url.lower():
                print('ERROR: Đăng nhập thất bại — kiểm tra GUIDE_CAPTURE_USER/PASSWORD', file=sys.stderr)
                browser.close()
                sys.exit(1)
            print('     OK')

            print('\n[Authenticated pages]')
            for name, path, mobile, wait_sel in SHOTS_AUTH:
                if name == '03-menu-mobile':
                    page.set_viewport_size({'width': 390, 'height': 844})
                    page.goto(BASE_URL + '/', wait_until='networkidle')
                    page.wait_for_selector('.portal-container', timeout=15000)
                    toggler = page.locator('[data-bs-target="#mobileMenu"]')
                    if toggler.count():
                        toggler.first.click()
                        page.wait_for_selector('#mobileMenu.show, #mobileMenu.offcanvas.show', timeout=5000)
                    page.wait_for_timeout(500)
                    out = OUTPUT / '03-menu-mobile.png'
                    page.screenshot(path=str(out), full_page=False)
                    print(f'     saved {out.name}')
                    continue
                capture(name, path, mobile, wait_sel)

            staff_u = STAFF_USER or USER
            staff_p = STAFF_PASSWORD or PASSWORD
            if staff_u and staff_p and (STAFF_USER or SHOTS_STAFF):
                print('\n[Staff pages]')
                page.goto(BASE_URL + '/accounts/logout/', wait_until='networkidle')
                page.goto(BASE_URL + '/accounts/login/', wait_until='networkidle')
                page.fill('input[name="username"]', staff_u)
                page.fill('input[name="password"]', staff_p)
                page.click('button[type="submit"]')
                page.wait_for_load_state('networkidle')
                for item in SHOTS_STAFF:
                    capture(*item)
        else:
            print('\n[Skip authenticated pages — set GUIDE_CAPTURE_USER & GUIDE_CAPTURE_PASSWORD]')

        browser.close()

    print('\nDone.')


if __name__ == '__main__':
    main()
