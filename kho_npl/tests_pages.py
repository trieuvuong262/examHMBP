from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from hrm.models import PermissionGroup, Profile
from hrm.module_permissions import MODULE_KHO_NPL
from hrm.permissions import ROLE_EMPLOYEE


class KhoNplPageSmokeTests(TestCase):
    """GET mọi trang chính — đảm bảo render 200, không lỗi template."""

    def setUp(self):
        self.user = User.objects.create_user(username='npl_smoke', password='test')
        Profile.objects.filter(user=self.user).update(role=ROLE_EMPLOYEE, is_employed=True)
        self.group = PermissionGroup.objects.create(
            name='NPL Smoke',
            module_permissions={
                MODULE_KHO_NPL: {
                    'view': True,
                    'create': True,
                    'update': True,
                    'delete': True,
                    'export': True,
                },
            },
        )
        profile = self.user.profile
        profile.permission_group = self.group
        profile.save(update_fields=['permission_group'])
        self.client.force_login(self.user)

    def _assert_ok(self, url_name, **kwargs):
        url = reverse(url_name, kwargs=kwargs)
        with self.subTest(url=url):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, msg=f'{url_name} returned {response.status_code}')

    def test_hub_and_overview(self):
        self._assert_ok('kho_npl:overview')
        self._assert_ok('kho_npl:stock_cards')

    def test_stock_alerts_pages(self):
        for url in (
            reverse('kho_npl:stock_alerts'),
            reverse('kho_npl:stock_alerts') + '?status=low',
            reverse('kho_npl:stock_alerts') + '?status=out',
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    def test_overview_links_to_stock_alerts(self):
        response = self.client.get(reverse('kho_npl:overview'))
        self.assertContains(response, reverse('kho_npl:stock_alerts') + '?status=low')
        self.assertContains(response, reverse('kho_npl:stock_alerts') + '?status=out')

    def test_overview_has_catalog_grid_layout(self):
        response = self.client.get(reverse('kho_npl:overview'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'npl-overview-table')
        self.assertContains(response, 'jp-mat-col-resizer')
        self.assertContains(response, 'jp-mat-th-sort')
        self.assertContains(response, 'Nhập Excel')
        self.assertContains(response, reverse('kho_npl:overview_export'))
        self.assertContains(response, 'jpNplCatalogLoading')
        self.assertContains(response, 'Đang tải tổng quan')

    def test_material_pages(self):
        for name in ('kho_npl:material_list', 'kho_npl:material_stock', 'kho_npl:material_create'):
            self._assert_ok(name)

    def test_material_stock_catalog_grid_layout(self):
        response = self.client.get(reverse('kho_npl:material_stock'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'npl-stock-table')
        self.assertContains(response, 'jp-mat-col-resizer')
        self.assertContains(response, 'value="" selected')
        self.assertNotContains(response, 'Thẻ kho (theo kệ)')
        self.assertNotContains(response, 'Cảnh báo thiếu')
        self.assertContains(response, reverse('kho_npl:material_stock_export'))
        self.assertContains(response, 'jpNplCatalogLoading')
        self.assertContains(response, 'Đang tải tồn kho')

    def test_stock_cards_catalog_grid_layout(self):
        response = self.client.get(reverse('kho_npl:stock_cards'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'npl-stock-card-catalog-table')
        self.assertContains(response, 'jp-mat-col-resizer')
        self.assertContains(response, 'jp-mat-th-sort')
        self.assertContains(response, 'jp-npl-catalog-row')
        self.assertContains(response, reverse('kho_npl:stock_cards_export'))
        self.assertContains(response, 'jpNplCatalogLoading')
        self.assertContains(response, 'Đang tải thẻ kho')

    def test_material_list_has_catalog_loading(self):
        response = self.client.get(reverse('kho_npl:material_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'jpNplCatalogLoading')
        self.assertContains(response, 'Đang tải danh mục')
        self.assertContains(response, 'catalog_page_loading.js?v=20260612a')

    def test_material_export_template(self):
        for name in ('kho_npl:material_export', 'kho_npl:material_import_template'):
            url = reverse(name)
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    def test_receipt_issue_pages(self):
        for name in (
            'kho_npl:receipt_list', 'kho_npl:receipt_create',
            'kho_npl:issue_list', 'kho_npl:issue_create',
        ):
            self._assert_ok(name)

    def test_doc_lists_catalog_grid_layout(self):
        pages = (
            ('kho_npl:receipt_list', 'npl-receipt-table'),
            ('kho_npl:issue_list', 'npl-issue-table'),
            ('kho_npl:disposal_list', 'npl-disposal-table'),
            ('kho_npl:stocktake_list', 'npl-stocktake-table'),
        )
        for url_name, table_id in pages:
            with self.subTest(url=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, table_id)
                self.assertContains(response, 'jp-mat-col-resizer')
                self.assertContains(response, 'jp-mat-th-sort')

    def test_transfer_hub_catalog_grid_layout(self):
        for tab in ('danh-sach', 'chuyen', 'nhan'):
            url = reverse('kho_npl:transfer_hub') + f'?tab={tab}'
            with self.subTest(tab=tab):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'npl-transfer-table')
                self.assertContains(response, 'jp-mat-col-resizer')
                self.assertContains(response, 'jp-npl-catalog-row')
                self.assertContains(response, "key === 'actions'")
                if tab != 'danh-sach':
                    self.assertContains(response, 'data-col="actions"')
                if tab in ('chuyen', 'nhan'):
                    self.assertContains(response, 'jp-npl-transfer-flow-btn')

    def test_transfer_pages(self):
        self._assert_ok('kho_npl:transfer_hub')
        create_resp = self.client.get(reverse('kho_npl:transfer_create'))
        self.assertEqual(create_resp.status_code, 302)
        self.assertIn('tab=nhap', create_resp.url)
        for tab in ('nhap', 'chuyen', 'nhan', 'danh-sach'):
            url = reverse('kho_npl:transfer_hub') + f'?tab={tab}'
            with self.subTest(tab=tab):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    def test_disposal_pages(self):
        for name in ('kho_npl:disposal_list', 'kho_npl:disposal_create'):
            self._assert_ok(name)

    def test_adjustment_stocktake_pages(self):
        for name in (
            'kho_npl:adjustment_list', 'kho_npl:adjustment_create',
            'kho_npl:stocktake_list', 'kho_npl:stocktake_create',
        ):
            self._assert_ok(name)

    def test_report_pages(self):
        for name in (
            'kho_npl:report_hub',
            'kho_npl:report_stock', 'kho_npl:report_alerts',
            'kho_npl:report_movement', 'kho_npl:report_issue_lsx',
            'kho_npl:report_stocktake_history', 'kho_npl:report_ledger',
        ):
            self._assert_ok(name)

    def test_report_exports(self):
        for name in (
            'kho_npl:report_stock_export', 'kho_npl:report_alerts_export',
            'kho_npl:report_movement_export', 'kho_npl:report_issue_lsx_export',
            'kho_npl:report_stocktake_history_export', 'kho_npl:report_ledger_export',
        ):
            url = reverse(name)
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertIn(
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    response.get('Content-Type', ''),
                )

    def test_settings_pages(self):
        self._assert_ok('kho_npl:settings_hub')
        for section in ('nhom', 'dvt', 'vi-tri', 'ncc'):
            self._assert_ok('kho_npl:settings_list', section=section)
            self._assert_ok('kho_npl:settings_create', section=section)
