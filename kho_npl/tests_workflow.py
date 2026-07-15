from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from hrm.models import PermissionGroup, Profile
from hrm.module_permissions import MODULE_KHO_NPL
from hrm.permissions import ROLE_EMPLOYEE
from kho_npl.choices import ADJUST_STATUS_APPROVED, ADJUST_STATUS_PENDING, STOCKTAKE_STATUS_DRAFT
from kho_npl.models import (
    MaterialBatch,
    Material,
    MaterialCategory,
    StockAdjustment,
    StockAdjustmentLine,
    StockBalance,
    Stocktake,
    StocktakeLine,
    Unit,
    WarehouseLocation,
)


class KhoNplWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='npl_wf', password='test')
        Profile.objects.filter(user=self.user).update(role=ROLE_EMPLOYEE, is_employed=True)
        self.group = PermissionGroup.objects.create(
            name='NPL Workflow',
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
        self.location = WarehouseLocation.objects.get(code='MAIN')
        self.material = Material.objects.create(
            code='WF-01', name='WF test', category=self.category, unit=self.unit,
        )
        StockBalance.objects.create(
            material=self.material, location=self.location, quantity=Decimal('50'),
        )
        self.batch = MaterialBatch.objects.create(
            material=self.material, code='LO-WF', unit_price=Decimal('10000'), quantity=Decimal('50'),
        )
        self.client.login(username='npl_wf', password='test')

    def test_adjustment_approve_updates_stock(self):
        adj = StockAdjustment.objects.create(
            number='DC-TEST-01',
            adjust_date=timezone.localdate(),
            reason='Test điều chỉnh',
            proposed_by=self.user,
            status=ADJUST_STATUS_PENDING,
        )
        StockAdjustmentLine.objects.create(
            adjustment=adj,
            material=self.material,
            location=self.location,
            system_qty=Decimal('50'),
            actual_qty=Decimal('45'),
            batch=self.batch,
        )
        self.client.post(reverse('kho_npl:adjustment_approve', args=[adj.pk]))
        adj.refresh_from_db()
        self.assertEqual(adj.status, ADJUST_STATUS_APPROVED)
        balance = StockBalance.objects.get(material=self.material, location=self.location)
        self.assertEqual(balance.quantity, Decimal('45'))

    def test_stocktake_close_applies_variance(self):
        st = Stocktake.objects.create(
            number='KK-TEST-01',
            name='Kỳ test',
            stocktake_date=timezone.localdate(),
            location=self.location,
            created_by=self.user,
            status=STOCKTAKE_STATUS_DRAFT,
        )
        StocktakeLine.objects.create(
            stocktake=st, material=self.material, location=self.location,
            system_qty=Decimal('50'), actual_qty=Decimal('48'),
            batch=self.batch,
        )
        from kho_npl.choices import STOCKTAKE_STATUS_COUNTING
        st.status = STOCKTAKE_STATUS_COUNTING
        st.save(update_fields=['status'])
        from kho_npl.services.stocktakes import close_stocktake
        close_stocktake(st, self.user)
        balance = StockBalance.objects.get(material=self.material, location=self.location)
        self.assertEqual(balance.quantity, Decimal('48'))

    def test_report_stock_export(self):
        response = self.client.get(reverse('kho_npl:report_stock_export'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            response['Content-Type'],
        )

    def test_material_search_with_location_shows_name_and_qty(self):
        url = (
            reverse('kho_npl:material_search')
            + f'?q=WF&location_id={self.location.pk}'
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        row = next(r for r in response.json()['results'] if r['code'] == 'WF-01')
        self.assertIn('WF TEST', row['text'])
        self.assertIn('50', row['text'])

    def test_balance_lookup_api(self):
        url = (
            reverse('kho_npl:balance_lookup')
            + f'?material_id={self.material.pk}&location_id={self.location.pk}'
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['qty_decimal'], '50.000')
        self.assertIn('WF TEST', data['text'])
        self.assertIn('50', data['text'])

    def test_stocktake_count_page_has_loading(self):
        st = Stocktake.objects.create(
            number='KK-UI-01',
            name='UI test',
            stocktake_date=timezone.localdate(),
            location=self.location,
            created_by=self.user,
            status=STOCKTAKE_STATUS_DRAFT,
        )
        from kho_npl.services.stocktakes import start_stocktake_counting
        start_stocktake_counting(st)
        response = self.client.get(reverse('kho_npl:stocktake_count', args=[st.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'jp-npl-stocktake-page')
        self.assertContains(response, 'Đang tải bảng kiểm kê')
        self.assertContains(response, 'stk-count-search')
        self.assertContains(response, 'jp-npl-stk-count-filter-btn')
        self.assertContains(response, 'jp-npl-stk-count-actions')
        from kho_npl.forms import StocktakeLineFormSet, STOCKTAKE_LINE_FORMSET_MAX
        self.assertGreater(STOCKTAKE_LINE_FORMSET_MAX, 1000)
        self.assertEqual(StocktakeLineFormSet.max_num, STOCKTAKE_LINE_FORMSET_MAX)

    def test_adjustment_create_form_has_stock_lookup(self):
        response = self.client.get(reverse('kho_npl:adjustment_create'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'jp-npl-material-select')
        self.assertContains(response, reverse('kho_npl:balance_lookup'))

    def test_stocktake_populate_scoped_to_location(self):
        other_loc = WarehouseLocation.objects.create(code='WH-B', name='Kho B', is_active=True)
        StockBalance.objects.create(
            material=self.material, location=other_loc, quantity=Decimal('99'),
        )
        st = Stocktake.objects.create(
            number='KK-LOC-01',
            name='Kiểm kê MAIN',
            stocktake_date=timezone.localdate(),
            location=self.location,
            created_by=self.user,
            status=STOCKTAKE_STATUS_DRAFT,
        )
        from kho_npl.services.stocktakes import populate_stocktake_lines
        count = populate_stocktake_lines(st)
        self.assertGreater(count, 0)
        self.assertTrue(st.lines.filter(location=self.location).exists())
        self.assertFalse(st.lines.filter(location=other_loc).exists())

    def test_issue_disposal_forms_have_stock_lookup(self):
        for url_name in ('kho_npl:issue_create', 'kho_npl:disposal_create'):
            response = self.client.get(reverse(url_name))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'jp-npl-material-select')
            self.assertContains(response, 'data-npl-doc-lines')
            self.assertContains(response, reverse('kho_npl:balance_lookup'))
