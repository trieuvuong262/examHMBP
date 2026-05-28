#!/usr/bin/env python3
"""Chụp màn hình portal.justplay.vn cho cẩm nang PDF Giám đốc."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(os.environ.get('GM_GUIDE_IMG_DIR', ROOT / 'docs' / 'images' / 'gm-guide'))
BASE_URL = os.environ.get('GUIDE_BASE_URL', 'https://portal.justplay.vn').rstrip('/')
USER = os.environ.get('GUIDE_CAPTURE_USER', 'demo_gm')
PASSWORD = os.environ.get('GUIDE_CAPTURE_PASSWORD', 'Demo@123')

# (filename, path, mobile, wait_selector, full_page)
SHOTS = [
    ('01-dang-nhap', '/accounts/login/', False, '.card-login', False),
    ('01-dang-nhap-mobile', '/accounts/login/', True, '.card-login', False),
    ('02-trang-chu', '/', False, '.portal-container', False),
    ('02-trang-chu-mobile', '/', True, '.portal-container', True),
    ('03-menu-mobile', '/', True, None, False),
    ('04-doi-mat-khau', '/change-password/', False, '.jp-page, .change-password-container, .card-login', False),
    ('05-thong-bao', '/announcements/', False, '.jp-page', False),
    ('05-thong-bao-mobile', '/announcements/', True, '.jp-page', True),
    ('06-bao-cao-hom-nay', '/reports/today/', False, '.jp-page', False),
    ('06-bao-cao-hom-nay-mobile', '/reports/today/', True, '.jp-page', True),
    ('06-bao-cao-team', '/reports/team/', False, '.jp-page', False),
    ('06-bao-cao-lich-su', '/reports/my/', False, '.jp-page', False),
    ('07-dao-tao', '/training/my-courses/', False, '.jp-page', False),
    ('08-kiem-tra', '/exams/', False, '.jp-page', False),
    ('09-kpi', '/kpi/', False, '.jp-page', True),
    ('10-dashboard', '/dashboard/', False, '.jp-page, .tab-content', False),
    ('11-nhan-su', '/dashboard/users/', False, '.jp-page, table', False),
    ('12-kanban', '/hr/admin/recruitment/kanban/', False, '.kanban-wrapper, .jp-page', False),
    ('13-vi-tri-tuyen-dung', '/hr/admin/recruitment/jobs/', False, '.jp-page', False),
    ('14-khoa-hoc-admin', '/training/admin/course/', False, '.jp-page', False),
    ('15-huong-dan', '/huong-dan/', False, '.jp-guide-page', True),
]


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('pip install playwright && python -m playwright install chromium', file=sys.stderr)
        sys.exit(1)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    print(f'Output: {OUTPUT}')

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(locale='vi-VN', ignore_https_errors=True)

        page.goto(BASE_URL + '/accounts/login/', wait_until='networkidle', timeout=60000)
        page.fill('input[name="username"]', USER)
        page.fill('input[name="password"]', PASSWORD)
        page.click('button[type="submit"]')
        page.wait_for_load_state('networkidle')
        if 'login' in page.url.lower():
            print('Login failed', file=sys.stderr)
            sys.exit(1)

        for name, path, mobile, wait_sel, full_page in SHOTS:
            if name.startswith('01-dang'):
                page.context.clear_cookies()
                page.goto(BASE_URL + path, wait_until='networkidle', timeout=60000)
            else:
                vp = {'width': 390, 'height': 844} if mobile else {'width': 1280, 'height': 900}
                page.set_viewport_size(vp)
                page.goto(BASE_URL + path, wait_until='networkidle', timeout=60000)

            if name == '03-menu-mobile':
                page.set_viewport_size({'width': 390, 'height': 844})
                page.goto(BASE_URL + '/', wait_until='networkidle')
                page.locator('[data-bs-target="#mobileMenu"]').first.click()
                page.wait_for_timeout(600)
            elif wait_sel:
                for sel in wait_sel.split(', '):
                    try:
                        page.wait_for_selector(sel.strip(), timeout=12000)
                        break
                    except Exception:
                        continue

            page.wait_for_timeout(350)
            out = OUTPUT / f'{name}.png'
            page.screenshot(path=str(out), full_page=full_page)
            print(f'  {out.name} ({out.stat().st_size // 1024} KB)')

            if name.startswith('01-dang'):
                page.goto(BASE_URL + '/accounts/login/', wait_until='networkidle')
                page.fill('input[name="username"]', USER)
                page.fill('input[name="password"]', PASSWORD)
                page.click('button[type="submit"]')
                page.wait_for_load_state('networkidle')

        browser.close()
    print('Done.')


if __name__ == '__main__':
    main()
