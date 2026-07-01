"""Playwright UI tests: popup validation + red highlight after Da hieu."""

from decimal import Decimal

from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse

from hrm.models import PermissionGroup, Profile
from hrm.module_permissions import MODULE_KHO_NPL
from hrm.permissions import ROLE_EMPLOYEE
from kho_npl.models import (
    Material,
    MaterialCategory,
    StockBalance,
    Unit,
    WarehouseLocation,
)

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


class KhoNplValidationPopupUiTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        if not HAS_PLAYWRIGHT:
            raise cls._skip_class('playwright not installed')
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        if HAS_PLAYWRIGHT:
            cls.browser.close()
            cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user(username='npl_val_ui', password='test')
        Profile.objects.filter(user=self.user).update(role=ROLE_EMPLOYEE, is_employed=True)
        self.group = PermissionGroup.objects.create(
            name='NPL Validation UI',
            module_permissions={
                MODULE_KHO_NPL: {
                    'view': True, 'create': True, 'update': True,
                    'delete': True, 'export': True,
                },
            },
        )
        profile = Profile.objects.get(user=self.user)
        profile.permission_group = self.group
        profile.save(update_fields=['permission_group'])

        self.category = MaterialCategory.objects.get(code='vai-chinh')
        self.unit = Unit.objects.get(code='met')
        self.from_loc = WarehouseLocation.objects.get(code='MAIN')
        self.to_loc = WarehouseLocation.objects.create(code='SUB-V', name='Kho phu val', is_active=True)
        self.material = Material.objects.create(
            code='VAL-NPL-01', name='NPL validation test', category=self.category, unit=self.unit,
        )
        StockBalance.objects.create(
            material=self.material, location=self.from_loc, quantity=Decimal('50'),
        )

        self.context = self.browser.new_context(locale='vi-VN', viewport={'width': 1400, 'height': 900})
        self.page = self.context.new_page()
        self._login()

    def tearDown(self):
        self.context.close()

    def _login(self):
        self.page.goto(f'{self.live_server_url}{reverse("login")}')
        self.page.fill('input[name="username"]', 'npl_val_ui')
        self.page.fill('input[name="password"]', 'test')
        self.page.click('button[type="submit"]')
        self.page.wait_for_load_state('networkidle')

    def _dismiss_validation_modal(self):
        modal = self.page.locator('#jpNplValidationModal')
        modal.wait_for(state='visible', timeout=8000)
        self.assertTrue(modal.locator('.jp-npl-validation-list-item').count() > 0)
        self.page.locator('#jpNplValidationModal button[data-bs-dismiss="modal"]').click()
        modal.wait_for(state='hidden', timeout=5000)

    def test_receipt_missing_fields_popup_and_red_supplier(self):
        url = f'{self.live_server_url}{reverse("kho_npl:receipt_create")}'
        self.page.goto(url)
        self.page.wait_for_selector('#receipt-form', timeout=10000)
        self.page.locator('#receipt-form button[type="submit"]').first.click()
        self.page.wait_for_load_state('networkidle')

        self._dismiss_validation_modal()

        supplier_select = self.page.locator('#receipt-form select.jp-npl-supplier-select')
        supplier_wrapper = supplier_select.locator('xpath=preceding-sibling::div[contains(@class,"ts-wrapper")]')
        self.assertTrue(
            supplier_wrapper.evaluate('el => el.classList.contains("is-invalid")'),
            'NCC Tom Select wrapper should be red after dismiss',
        )
        ts_control = supplier_wrapper.locator('.ts-control')
        self.assertTrue(
            ts_control.evaluate('el => el.classList.contains("is-invalid")'),
            'NCC dropdown control should be red after dismiss',
        )
        label = self.page.locator('label[for="id_supplier"]')
        self.assertTrue(
            label.evaluate('el => el.classList.contains("jp-npl-label-invalid")'),
            'NCC label should be red after dismiss',
        )

    def test_transfer_invalid_qty_popup_and_red_qty_after_dismiss(self):
        url = f'{self.live_server_url}{reverse("kho_npl:transfer_hub")}?tab=nhap'
        self.page.goto(url)
        self.page.wait_for_selector('#transfer-form', timeout=10000)

        self.page.select_option('#id_from_location', str(self.from_loc.pk))
        self.page.select_option('#id_to_location', str(self.to_loc.pk))

        material_select = self.page.locator('#lines-body .line-row').first.locator('select.jp-npl-material-select')
        material_select.wait_for(state='attached', timeout=5000)
        material_select.select_option(str(self.material.pk))
        self.page.wait_for_timeout(800)

        qty_input = self.page.locator('#lines-body input[name$="-quantity"]').first
        qty_input.fill('999')
        qty_input.dispatch_event('input')
        qty_input.dispatch_event('change')

        modal = self.page.locator('#jpNplValidationModal')
        modal.wait_for(state='visible', timeout=8000)
        title = modal.locator('.jp-npl-validation-title-text').inner_text()
        self.assertIn('S\u1ed1 l\u01b0\u1ee3ng kh\u00f4ng h\u1ee3p l\u1ec7', title)
        self.assertTrue(
            modal.locator('.jp-npl-validation-list-item').filter(has_text='v\u01b0\u1ee3t t\u1ed3n').count() > 0,
        )

        self._dismiss_validation_modal()

        self.assertTrue(
            qty_input.evaluate('el => el.classList.contains("is-invalid")'),
            'Qty input should stay red after dismiss',
        )
        qty_td = qty_input.locator('xpath=ancestor::td[1]')
        self.assertTrue(
            qty_td.evaluate('el => el.classList.contains("jp-npl-cell-invalid")'),
            'Qty cell should be highlighted after dismiss',
        )
        qty_th = self.page.locator('.jp-npl-transfer-lines-table thead th.jp-npl-col-qty')
        self.assertTrue(
            qty_th.evaluate('el => el.classList.contains("jp-npl-label-invalid")'),
            'Qty column header should be red after dismiss',
        )

    def test_transfer_zero_qty_popup_and_red_after_dismiss(self):
        url = f'{self.live_server_url}{reverse("kho_npl:transfer_hub")}?tab=nhap'
        self.page.goto(url)
        self.page.wait_for_selector('#transfer-form', timeout=10000)

        self.page.select_option('#id_from_location', str(self.from_loc.pk))
        self.page.select_option('#id_to_location', str(self.to_loc.pk))

        material_select = self.page.locator('#lines-body .line-row').first.locator('select.jp-npl-material-select')
        material_select.select_option(str(self.material.pk))
        self.page.wait_for_timeout(500)

        qty_input = self.page.locator('#lines-body input[name$="-quantity"]').first
        qty_input.fill('0')
        qty_input.dispatch_event('input')
        qty_input.dispatch_event('change')

        modal = self.page.locator('#jpNplValidationModal')
        modal.wait_for(state='visible', timeout=8000)
        self.assertTrue(
            modal.locator('.jp-npl-validation-list-item').filter(has_text='l\u1edbn h\u01a1n 0').count() > 0,
        )

        self._dismiss_validation_modal()

        self.assertTrue(
            qty_input.evaluate('el => el.classList.contains("is-invalid")'),
            'Zero qty input should stay red after dismiss',
        )
