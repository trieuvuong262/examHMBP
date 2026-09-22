#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tạo việc demo trên portal.justplay.vn và chụp từng bước hướng dẫn.

  python scripts/capture_cong_viec_fleetd.py
  python scripts/capture_cong_viec_fleetd.py --resume   # bỏ qua tạo việc, tiếp từ NV
"""
from __future__ import annotations

import shutil
import sys
from datetime import date, timedelta
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
TITLE = 'setup fleetd-base trên VPS'
TODAY = date.today()
DUE = TODAY + timedelta(days=15)
VIEWPORT = {'width': 1440, 'height': 2400}

DESC = (
    'Cài đặt và cấu hình fleetd-base trên VPS.\n'
    '- Kiểm tra OS/SSH vào VPS\n'
    '- Cài fleetd-base\n'
    '- Cấu hình dịch vụ và xác nhận chạy OK\n'
    f'Thời hạn thực hiện: 15 ngày (hạn đến {DUE.strftime("%d/%m/%Y")}).'
)


def shot(page, name: str, *, full=False):
    OUT.mkdir(parents=True, exist_ok=True)
    page.wait_for_timeout(250)
    path = OUT / f'{name}.png'
    page.screenshot(path=str(path), full_page=full)
    print(f'  saved {path.name} ({path.stat().st_size // 1024} KB)  {page.url}')
    return path


def wait_page(page, sel='.jp-page, .card-login, .portal-container'):
    page.wait_for_load_state('networkidle')
    for part in sel.split(','):
        try:
            page.wait_for_selector(part.strip(), timeout=15000)
            return
        except PwTimeout:
            continue


def login(page, username, password, shot_name=None):
    page.goto(BASE + '/accounts/login/', wait_until='networkidle', timeout=90000)
    wait_page(page, '.card-login, input[name="username"]')
    page.fill('input[name="username"]', username)
    page.fill('input[name="password"]', password)
    if shot_name:
        page.set_viewport_size({'width': 1440, 'height': 900})
        shot(page, shot_name, full=False)
        page.set_viewport_size(VIEWPORT)
    page.click('button[type="submit"]')
    page.wait_for_load_state('networkidle')
    if '/login' in page.url.lower() and 'change-password' not in page.url.lower():
        raise RuntimeError(f'Dang nhap that bai: {username} -> {page.url}')
    if 'change-password' in page.url.lower() or 'doi-mat-khau' in page.url.lower():
        print(f'  note: {username} force password change, skip to module')


def logout(page):
    btn = page.locator('button:has-text("Đăng xuất")').first
    if btn.count():
        btn.click()
        page.wait_for_load_state('networkidle')
    else:
        page.context.clear_cookies()
        page.goto(BASE + '/accounts/login/', wait_until='networkidle')


def pick_assignee(page, username: str):
    toggle = page.locator('.jp-user-picker-toggle').first
    toggle.click()
    menu = page.locator('.jp-user-picker-menu').first
    menu.wait_for(state='visible', timeout=10000)
    search = page.locator('.jp-user-picker-search').first
    search.fill(username)
    page.wait_for_timeout(400)
    opt = page.locator('.jp-user-picker-option').filter(has_text=username).first
    if not opt.count():
        opt = page.locator(f'.jp-user-picker-option[data-search*="{username.lower()}"]').first
    if not opt.count():
        raise RuntimeError(f'Khong thay nguoi nhan {username} trong picker')
    opt.click()
    page.wait_for_timeout(300)
    shot(page, 'cong-viec-picker')
    page.keyboard.press('Escape')
    page.wait_for_timeout(200)


def open_task_row(page, title: str):
    row = page.locator('table tbody tr').filter(has_text=title).first
    row.wait_for(timeout=15000)
    row.locator('a:has-text("Chi tiết")').click()
    wait_page(page)
    page.wait_for_selector('h2.jp-page-title, .jp-page-title', timeout=20000)


def copy_alias(src: str, *aliases: str):
    origin = OUT / f'{src}.png'
    if not origin.exists():
        return
    for name in aliases:
        shutil.copy2(origin, OUT / f'{name}.png')


def main():
    skip_create = '--resume' in sys.argv
    OUT.mkdir(parents=True, exist_ok=True)
    print(f'Base={BASE} resume={skip_create}')
    print(f'Task={TITLE} due={DUE.isoformat()} complete={TODAY.isoformat()}')

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale='vi-VN',
            timezone_id='Asia/Ho_Chi_Minh',
            color_scheme='light',
            ignore_https_errors=True,
            viewport=VIEWPORT,
        )
        page = context.new_page()
        page.set_default_timeout(30000)

        if not skip_create:
            print('\n[QL] Login Vuonglnt')
            login(page, MGR_USER, MGR_PASS, 'cong-viec-login-ql')

            print('[QL] Da giao')
            page.goto(BASE + '/cong-viec/ca-nhan/da-giao/', wait_until='networkidle', timeout=90000)
            wait_page(page)
            shot(page, 'cong-viec-da-giao')

            print('[QL] Viec lap')
            page.goto(BASE + '/cong-viec/ca-nhan/lap-lai/', wait_until='networkidle', timeout=90000)
            wait_page(page)
            shot(page, 'cong-viec-lap-lai')

            print('[QL] Form giao viec')
            page.goto(BASE + '/cong-viec/ca-nhan/giao/', wait_until='networkidle', timeout=90000)
            wait_page(page)
            shot(page, 'cong-viec-form')

            page.fill('#id_title', TITLE)
            page.fill('#id_description', DESC)
            page.select_option('#id_task_type', 'GENERAL')
            page.select_option('#id_priority', 'HIGH')
            page.fill('#id_due_date', DUE.isoformat())
            for cid in ('#id_skip_completion_review', '#id_is_recurring'):
                box = page.locator(cid)
                if box.count() and box.is_checked():
                    box.uncheck()

            print('[QL] Chon long.tb')
            pick_assignee(page, EMP_USER)
            shot(page, 'cong-viec-form-filled')

            print('[QL] Submit')
            page.get_by_role('button', name='Giao việc', exact=True).click()
            page.wait_for_load_state('networkidle')
            wait_page(page)
            if '/giao/' in page.url:
                shot(page, 'cong-viec-form-error')
                raise RuntimeError('Giao viec that bai')
            shot(page, 'cong-viec-chi-tiet-moi')

            page.goto(BASE + '/cong-viec/ca-nhan/da-giao/?q=fleetd', wait_until='networkidle')
            wait_page(page)
            shot(page, 'cong-viec-da-giao-cho-xac-nhan')
            logout(page)
        else:
            print('\n[QL] skip create (--resume)')

        print('\n[NV] Login long.tb')
        login(page, EMP_USER, EMP_PASS, 'cong-viec-login-nv')

        print('[NV] Viec cua toi')
        page.goto(BASE + '/cong-viec/ca-nhan/cua-toi/?q=fleetd', wait_until='networkidle')
        wait_page(page)
        shot(page, 'cong-viec-cua-toi')

        open_task_row(page, TITLE)
        reject_btn = page.get_by_role('button', name='Từ chối', exact=True)
        if reject_btn.count():
            reject_btn.click()
            page.wait_for_timeout(400)
        shot(page, 'cong-viec-xac-nhan')

        print('[NV] Xac nhan')
        page.get_by_role('button', name='Xác nhận nhận việc', exact=True).click()
        page.wait_for_load_state('networkidle')
        wait_page(page)
        shot(page, 'cong-viec-dang-lam')

        print('[NV] Tien do 50%')
        slider = page.locator('input.jp-progress-slider, input[type="range"][name="progress_percent"]').first
        if slider.count():
            slider.fill('50')
        progress_form = page.locator('form:has(input[name="action"][value="progress"])')
        if progress_form.count():
            progress_form.locator('textarea').fill('Đã SSH vào VPS, đang cài fleetd-base.')
        shot(page, 'cong-viec-tien-do')
        page.get_by_role('button', name='Lưu tiến độ', exact=True).click()
        page.wait_for_load_state('networkidle')
        wait_page(page)
        print('[NV]Nop cho duyet')
        submit_form = page.locator('form:has(input[name="action"][value="submit"])')
        submit_form.locator('textarea').fill(
            f'Hoàn tất setup fleetd-base trên VPS ngày {TODAY.strftime("%d/%m/%Y")}.\n'
            '- Dịch vụ fleetd-base đang chạy\n'
            '- Đã kiểm tra health/basic check OK'
        )
        shot(page, 'cong-viec-nop')
        page.get_by_role('button', name='Nộp chờ duyệt', exact=True).click()
        page.wait_for_load_state('networkidle')
        wait_page(page)
        shot(page, 'cong-viec-nv-cho-duyet')
        logout(page)

        print('\n[QL] Duyet')
        login(page, MGR_USER, MGR_PASS)

        page.goto(BASE + '/cong-viec/ca-nhan/da-giao/?status=pending_review&q=fleetd', wait_until='networkidle')
        wait_page(page)
        shot(page, 'cong-viec-da-giao-cho-duyet')

        open_task_row(page, TITLE)
        review_form = page.locator('form:has(input[name="action"][value="approve"])')
        if review_form.count():
            review_form.locator('textarea').fill(
                'Đã kiểm tra — fleetd-base OK trên VPS. Duyệt hoàn thành trong ngày.'
            )
        shot(page, 'cong-viec-duyet')

        print('[QL] Duyet hoan thanh')
        page.get_by_role('button', name='Duyệt hoàn thành', exact=True).click()
        page.wait_for_load_state('networkidle')
        wait_page(page)
        shot(page, 'cong-viec-hoan-thanh')

        page.goto(BASE + '/cong-viec/ca-nhan/da-giao/?q=fleetd', wait_until='networkidle')
        wait_page(page)
        shot(page, 'cong-viec-da-giao-xong')

        browser.close()

    copy_alias('cong-viec-cua-toi', 'cong-viec-01')
    copy_alias('cong-viec-xac-nhan', 'cong-viec-02')
    copy_alias('cong-viec-tien-do', 'cong-viec-03', 'cong-viec-04')
    copy_alias('cong-viec-da-giao', 'cong-viec-05')
    copy_alias('cong-viec-da-giao-cho-xac-nhan', 'cong-viec-06')
    copy_alias('cong-viec-form', 'cong-viec-07', 'cong-viec-09')
    copy_alias('cong-viec-duyet', 'cong-viec-08')
    copy_alias('cong-viec-lap-lai', 'cong-viec-10')
    print('\nDone.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
