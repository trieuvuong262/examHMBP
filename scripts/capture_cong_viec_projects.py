#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Chụp màn Dự án nội bộ + Liên phòng ban trên portal.justplay.vn."""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import TimeoutError as PwTimeout
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'static' / 'images' / 'guide'
BASE = 'https://portal.justplay.vn'
MGR_USER = 'Vuonglnt'
MGR_PASS = '123123sS@@'
EMP_USER = 'long.tb'
EMP_PASS = 'Abc@123123'
VIEWPORT = {'width': 1440, 'height': 1600}


def shot(page, name: str):
    OUT.mkdir(parents=True, exist_ok=True)
    page.wait_for_timeout(280)
    path = OUT / f'{name}.png'
    page.screenshot(path=str(path), full_page=False)
    print(f'  saved {path.name} ({path.stat().st_size // 1024} KB)  {page.url}')


def wait_page(page):
    page.wait_for_load_state('networkidle')
    try:
        page.wait_for_selector('.jp-page, .card-login', timeout=20000)
    except PwTimeout:
        pass


def login(page, username, password):
    page.goto(BASE + '/accounts/login/', wait_until='networkidle', timeout=90000)
    wait_page(page)
    page.fill('input[name="username"]', username)
    page.fill('input[name="password"]', password)
    page.click('button[type="submit"]')
    page.wait_for_load_state('networkidle')
    if '/login' in page.url.lower() and 'change-password' not in page.url.lower():
        raise RuntimeError(f'login failed {username}')


def logout(page):
    btn = page.locator('button:has-text("Đăng xuất")').first
    if btn.count():
        btn.click()
        page.wait_for_load_state('networkidle')
    else:
        page.context.clear_cookies()


def go(page, path):
    page.goto(BASE + path, wait_until='networkidle', timeout=90000)
    wait_page(page)


def crop_whitespace(name: str, content_x0=270):
    import numpy as np
    from PIL import Image

    path = OUT / f'{name}.png'
    if not path.exists():
        return
    im = Image.open(path).convert('RGB')
    arr = np.array(im)
    h, w, _ = arr.shape
    if h < 900:
        return
    region = arr[:, content_x0:w - 8, :]
    dark = (region < 248).any(axis=2).any(axis=1)
    scan_to = max(1, h - 60)
    idxs = np.where(dark[:scan_to])[0]
    if len(idxs) == 0:
        return
    new_h = min(h, int(idxs[-1]) + 28)
    if new_h >= h - 10:
        return
    im.crop((0, 0, w, new_h)).save(path, optimize=True)
    print(f'  crop {name} {h} -> {new_h}')


def main():
    names = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            locale='vi-VN',
            timezone_id='Asia/Ho_Chi_Minh',
            color_scheme='light',
            ignore_https_errors=True,
            viewport=VIEWPORT,
        )
        page.set_default_timeout(30000)

        print('[QL] Du an noi bo')
        login(page, MGR_USER, MGR_PASS)
        go(page, '/cong-viec/du-an/')
        shot(page, 'cong-viec-du-an-list')
        names.append('cong-viec-du-an-list')

        go(page, '/cong-viec/du-an/tao/')
        shot(page, 'cong-viec-du-an-tao')
        names.append('cong-viec-du-an-tao')

        link = page.locator('a.btn-outline-hm:has-text("Chi tiết")').first
        # may be on create page; go list again
        go(page, '/cong-viec/du-an/')
        detail = page.locator('table a:has-text("Chi tiết")').first
        if detail.count():
            detail.click()
            page.wait_for_load_state('networkidle')
            wait_page(page)
            shot(page, 'cong-viec-du-an-chitiet')
            names.append('cong-viec-du-an-chitiet')

        print('[QL] Lien phong ban')
        go(page, '/cong-viec/lien-phong-ban/')
        shot(page, 'cong-viec-lpb-list')
        names.append('cong-viec-lpb-list')

        go(page, '/cong-viec/lien-phong-ban/cho-tiep-nhan/')
        shot(page, 'cong-viec-lpb-cho')
        names.append('cong-viec-lpb-cho')

        go(page, '/cong-viec/lien-phong-ban/tao/')
        wait_page(page)
        shot(page, 'cong-viec-lpb-tao')
        names.append('cong-viec-lpb-tao')

        go(page, '/cong-viec/lien-phong-ban/')
        d2 = page.locator('table a:has-text("Chi tiết")').first
        if d2.count():
            d2.click()
            page.wait_for_load_state('networkidle')
            wait_page(page)
            shot(page, 'cong-viec-lpb-chitiet')
            names.append('cong-viec-lpb-chitiet')

        logout(page)

        print('[NV] lists')
        login(page, EMP_USER, EMP_PASS)
        go(page, '/cong-viec/du-an/')
        shot(page, 'cong-viec-du-an-nv')
        names.append('cong-viec-du-an-nv')
        go(page, '/cong-viec/lien-phong-ban/')
        shot(page, 'cong-viec-lpb-nv')
        names.append('cong-viec-lpb-nv')
        go(page, '/cong-viec/lien-phong-ban/cho-tiep-nhan/')
        shot(page, 'cong-viec-lpb-cho-nv')
        names.append('cong-viec-lpb-cho-nv')

        browser.close()

    for n in names:
        crop_whitespace(n)
    print('Done.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
