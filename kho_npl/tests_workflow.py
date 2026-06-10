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
    Material,
    MaterialCategory,
    StockAdjustment,
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
        self.client.login(username='npl_wf', password='test')

    def test_adjustment_approve_updates_stock(self):
        adj = StockAdjustment.objects.create(
            number='DC-TEST-01',
            adjust_date=timezone.localdate(),
            material=self.material,
            location=self.location,
            system_qty=Decimal('50'),
            actual_qty=Decimal('45'),
            reason='Test điều chỉnh',
            proposed_by=self.user,
            status=ADJUST_STATUS_PENDING,
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
            created_by=self.user,
            status=STOCKTAKE_STATUS_DRAFT,
        )
        StocktakeLine.objects.create(
            stocktake=st, material=self.material, location=self.location,
            system_qty=Decimal('50'), actual_qty=Decimal('48'),
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
