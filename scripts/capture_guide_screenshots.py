#!/usr/bin/env python3
"""
Chụp màn hình portal.justplay.vn cho trang Hướng dẫn (desktop 1280px).

Usage:
  pip install playwright
  playwright install chromium

  set GUIDE_CAPTURE_USER=admin
  set GUIDE_CAPTURE_PASSWORD=123123sS
  python scripts/capture_guide_screenshots.py
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUTPUT = Path(os.environ.get('GUIDE_OUTPUT_DIR', ROOT / 'static' / 'images' / 'guide'))
BASE_URL = os.environ.get('GUIDE_BASE_URL', 'https://portal.justplay.vn').rstrip('/')
USER = os.environ.get('GUIDE_CAPTURE_USER', '')
PASSWORD = os.environ.get('GUIDE_CAPTURE_PASSWORD', '')
VIEWPORT = {'width': 1280, 'height': 900}

# (filename, path, wait_selector)
SHOTS_PUBLIC = [
    ('01-dang-nhap', '/accounts/login/', '.card-login'),
]

SHOTS_AUTH = [
    ('02-trang-chu', '/', '.portal-container'),
    ('04-doi-mat-khau', '/change-password/', '.change-password-container, .card-login, .jp-page'),
    ('05-thong-bao', '/announcements/', '.jp-page'),
    ('06-bao-cao', '/reports/today/', '.jp-page'),
    ('07-dao-tao', '/training/my-courses/', '.jp-page'),
    ('08-kiem-tra', '/exams/', '.jp-page'),
    ('09-kpi', '/kpi/', '.jp-page'),
    ('10-nhan-su', '/dashboard/users/', '.jp-hrm-page, .jp-page, table'),
    ('11-phan-quyen', '/dashboard/permissions/', '.jp-page, form, table'),
    ('12-tai-lieu', '/tai-lieu/', '.jp-page'),
    ('13-cong-viec', '/cong-viec/ca-nhan/', '.jp-page'),
    ('14-de-xuat', '/yeu-cau/de-xuat/cua-toi/', '.jp-page'),
    ('15-ho-tro', '/yeu-cau/ho-tro/cua-toi/', '.jp-page'),
    ('16-thiet-bi', '/thiet-bi/it/', '.jp-page'),
    ('17-gop-y', '/gop-y/', '.jp-page'),
    ('18-kho-npl', '/kho-npl/tong-quan/', '.jp-page'),
    ('19-kiotviet', '/kiotviet/khach-hang/', '.jp-page'),
    ('20-nas', '/thu-muc-nas/', '.jp-page'),
    ('21-tuyen-dung', '/hr/admin/recruitment/kanban/', '.kanban-wrapper, .jp-page'),
    ('22-audit', '/nhat-ky/', '.jp-page'),
    ('23-huong-dan', '/huong-dan/', '.jp-guide-page'),
]


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('Cần cài: pip install playwright && playwright install chromium', file=sys.stderr)
        sys.exit(1)

    from hrm.guide_step_shots import STEP_SCREENSHOTS

    OUTPUT.mkdir(parents=True, exist_ok=True)
    print(f'Base URL: {BASE_URL}')
    print(f'Output:   {OUTPUT}')

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale='vi-VN',
            color_scheme='light',
            ignore_https_errors=True,
            viewport=VIEWPORT,
        )
        page = context.new_page()
        url_cache: dict[tuple[str, str], Path] = {}

        def capture(name: str, path: str, wait_sel: str | None):
            url = BASE_URL + path
            cache_key = (path, wait_sel or '')
            if cache_key in url_cache:
                src = url_cache[cache_key]
                out = OUTPUT / f'{name}.png'
                shutil.copy2(src, out)
                print(f'  -> {name}.png  (copy from {src.name})')
                return

            print(f'  -> {name}.png  {url}')
            page.goto(url, wait_until='networkidle', timeout=90000)
            if wait_sel:
                for sel in wait_sel.split(', '):
                    try:
                        page.wait_for_selector(sel.strip(), timeout=20000)
                        break
                    except Exception:
                        continue
            page.wait_for_timeout(500)
            out = OUTPUT / f'{name}.png'
            page.screenshot(path=str(out), full_page=False)
            url_cache[cache_key] = out
            print(f'     saved {out.name} ({out.stat().st_size // 1024} KB)')

        print('\n[Public pages]')
        for item in SHOTS_PUBLIC:
            capture(*item)

        if not (USER and PASSWORD):
            print('\n[Skip authenticated — set GUIDE_CAPTURE_USER & GUIDE_CAPTURE_PASSWORD]')
            browser.close()
            return

        print('\n[Login]')
        page.goto(BASE_URL + '/accounts/login/', wait_until='networkidle')
        page.fill('input[name="username"]', USER)
        page.fill('input[name="password"]', PASSWORD)
        page.click('button[type="submit"]')
        page.wait_for_load_state('networkidle')
        if '/login' in page.url or 'login' in page.url.lower():
            print('ERROR: Đăng nhập thất bại', file=sys.stderr)
            browser.close()
            sys.exit(1)
        print('     OK')

        print('\n[Overview screenshots — desktop]')
        for name, path, wait_sel in SHOTS_AUTH:
            capture(name, path, wait_sel)

        print(f'\n[Step screenshots — {len(STEP_SCREENSHOTS)} files]')
        for name, (path, wait_sel) in sorted(STEP_SCREENSHOTS.items()):
            capture(name, path, wait_sel)

        from hrm.guide_step_shots import SECTION_FALLBACK
        print('\n[Fallback copies for missing step images]')
        for name in STEP_SCREENSHOTS:
            out = OUTPUT / f'{name}.png'
            if out.exists():
                continue
            section = name.rsplit('-', 1)[0]
            fb = SECTION_FALLBACK.get(section)
            if fb and (OUTPUT / fb).exists():
                shutil.copy2(OUTPUT / fb, out)
                print(f'  -> {name}.png from {fb}')

        browser.close()

    print('\nDone.')


if __name__ == '__main__':
    main()
