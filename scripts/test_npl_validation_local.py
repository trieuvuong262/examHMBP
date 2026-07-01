#!/usr/bin/env python3
"""Test popup validation + red highlight on local dev server."""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')

import django
django.setup()

from django.contrib.auth.models import User

from hrm.models import PermissionGroup, Profile
from hrm.module_permissions import MODULE_KHO_NPL
from hrm.permissions import ROLE_EMPLOYEE
from kho_npl.models import Material, MaterialCategory, StockBalance, Unit, WarehouseLocation

BASE_URL = os.environ.get('NPL_TEST_BASE_URL', 'http://127.0.0.1:8000').rstrip('/')
USERNAME = 'npl_popup_tester'
PASSWORD = 'test-popup-123'


def ensure_fixtures():
    user, _ = User.objects.get_or_create(username=USERNAME, defaults={'is_active': True})
    user.set_password(PASSWORD)
    user.save()
    Profile.objects.filter(user=user).update(role=ROLE_EMPLOYEE, is_employed=True)
    group, _ = PermissionGroup.objects.get_or_create(
        name='NPL Popup Tester',
        defaults={
            'module_permissions': {
                MODULE_KHO_NPL: {
                    'view': True, 'create': True, 'update': True,
                    'delete': True, 'export': True,
                },
            },
        },
    )
    profile = Profile.objects.get(user=user)
    profile.permission_group = group
    profile.save(update_fields=['permission_group'])

    category = MaterialCategory.objects.get(code='vai-chinh')
    unit = Unit.objects.get(code='met')
    from_loc = WarehouseLocation.objects.get(code='MAIN')
    to_loc, _ = WarehouseLocation.objects.get_or_create(
        code='SUB-POPUP', defaults={'name': 'Kho popup test', 'is_active': True},
    )
    material, _ = Material.objects.get_or_create(
        code='POPUP-NPL-01',
        defaults={
            'name': 'NPL popup test', 'category': category, 'unit': unit, 'is_active': True,
        },
    )
    StockBalance.objects.update_or_create(
        material=material, location=from_loc,
        defaults={'quantity': Decimal('50')},
    )
    return {
        'from_loc': from_loc.pk,
        'to_loc': to_loc.pk,
        'material': material.pk,
    }


def login(page):
    page.goto(BASE_URL + '/accounts/login/', wait_until='networkidle', timeout=60000)
    page.fill('input[name="username"]', USERNAME)
    page.fill('input[name="password"]', PASSWORD)
    page.click('button[type="submit"]')
    page.wait_for_load_state('networkidle')


def dismiss_modal(page):
    modal = page.locator('#jpNplValidationModal')
    modal.wait_for(state='visible', timeout=10000)
    items = modal.locator('.jp-npl-validation-list-item').count()
    assert items > 0, 'Modal should list errors'
    page.get_by_role("button", name="Đã hiểu").click()
    modal.wait_for(state='hidden', timeout=5000)


def test_receipt_missing_supplier(page):
    print('TEST receipt missing supplier...')
    page.goto(BASE_URL + '/kho-npl/phieu-nhap/them/', wait_until='networkidle', timeout=60000)
    page.wait_for_selector('#receipt-form', timeout=15000)
    page.locator('#receipt-form button[type="submit"]').first.click()
    page.wait_for_load_state('networkidle')
    dismiss_modal(page)

    wrapper = page.locator('#receipt-form .flex-grow-1 .ts-wrapper.is-invalid').first
    assert wrapper.count() > 0, 'supplier ts-wrapper not red'
    assert wrapper.locator('.ts-control').evaluate('el => el.classList.contains("is-invalid")'), 'supplier control not red'
    assert page.locator('#id_supplier').evaluate('el => el.classList.contains("is-invalid")'), 'supplier select not marked'
    label = page.locator('label.form-label', has_text='Nhà cung cấp')
    assert label.evaluate('el => el.classList.contains("jp-npl-label-invalid")')
    print('  OK')



def setup_transfer_line(page, fx):
    page.select_option('#id_from_location', str(fx['from_loc']))
    page.select_option('#id_to_location', str(fx['to_loc']))
    page.evaluate(
        """(args) => {
            const row = document.querySelector('#lines-body .line-row');
            if (!row) return false;
            const sel = row.querySelector('select.jp-npl-material-select');
            if (!sel || !sel.tomselect) return false;
            const ts = sel.tomselect;
            const id = String(args.materialId);
            ts.addOption({ id: id, name: args.name, text: args.name, unit: 'm' });
            ts.setValue(id, true);
            const stockEl = row.querySelector('.jp-npl-stock-qty');
            if (stockEl) {
                stockEl.dataset.stockQty = String(args.stock);
                stockEl.textContent = args.stock + ' m';
            }
            return true;
        }""",
        {'materialId': fx['material'], 'name': 'POPUP-NPL-01', 'stock': 50},
    )

def test_transfer_over_stock(page, fx):
    print('TEST transfer qty over stock...')
    page.goto(BASE_URL + '/kho-npl/chuyen-kho/?tab=nhap', wait_until='networkidle', timeout=60000)
    page.wait_for_selector('#transfer-form', timeout=15000)
    setup_transfer_line(page, fx)
    page.wait_for_timeout(300)
    qty = page.locator('#lines-body input[name$="-quantity"]').first
    qty.fill('999')
    qty.dispatch_event('input')
    qty.dispatch_event('change')
    modal = page.locator('#jpNplValidationModal')
    modal.wait_for(state='visible', timeout=10000)
    title = modal.locator('.jp-npl-validation-title-text').inner_text()
    assert 'S\u1ed1 l\u01b0\u1ee3ng kh\u00f4ng h\u1ee3p l\u1ec7' in title, title
    dismiss_modal(page)
    assert qty.evaluate('el => el.classList.contains("is-invalid")'), 'qty not red after dismiss'
    assert qty.locator('xpath=ancestor::td[1]').evaluate('el => el.classList.contains("jp-npl-cell-invalid")')
    assert page.locator('.jp-npl-transfer-lines-table thead th.jp-npl-col-qty').evaluate(
        'el => el.classList.contains("jp-npl-label-invalid")'
    )
    print('  OK')


def test_transfer_zero_qty(page, fx):
    print('TEST transfer qty zero...')
    page.goto(BASE_URL + '/kho-npl/chuyen-kho/?tab=nhap', wait_until='networkidle', timeout=60000)
    page.wait_for_selector('#transfer-form', timeout=15000)
    setup_transfer_line(page, fx)
    page.wait_for_timeout(300)
    qty = page.locator('#lines-body input[name$="-quantity"]').first
    qty.fill('0')
    qty.dispatch_event('input')
    qty.dispatch_event('change')
    page.locator('#jpNplValidationModal').wait_for(state='visible', timeout=10000)
    dismiss_modal(page)
    assert qty.evaluate('el => el.classList.contains("is-invalid")'), 'zero qty not red after dismiss'
    print('  OK')


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('pip install playwright && playwright install chromium', file=sys.stderr)
        return 1

    fx = ensure_fixtures()
    print(f'Base URL: {BASE_URL}')
    print(f'User: {USERNAME}')

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale='vi-VN', viewport={'width': 1400, 'height': 900})
        page = context.new_page()
        login(page)
        test_receipt_missing_supplier(page)
        test_transfer_over_stock(page, fx)
        test_transfer_zero_qty(page, fx)
        browser.close()

    print('ALL PASSED')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
