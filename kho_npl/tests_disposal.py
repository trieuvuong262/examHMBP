from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from hrm.models import PermissionGroup, Profile
from hrm.module_permissions import MODULE_KHO_NPL
from hrm.permissions import ROLE_EMPLOYEE
from kho_npl.choices import DOC_STATUS_POSTED, WAREHOUSE_SCRAP_CODE
from kho_npl.models import (
    Material,
    MaterialCategory,
    StockBalance,
    StockDisposal,
    StockDisposalLine,
    StockLedger,
    Unit,
    WarehouseLocation,
)
from kho_npl.services.disposals import post_stock_disposal


class StockDisposalWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='npl_dis', password='test')
        Profile.objects.filter(user=self.user).update(role=ROLE_EMPLOYEE, is_employed=True)
        self.group = PermissionGroup.objects.create(
            name='NPL Disposal',
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
        self.scrap_loc = WarehouseLocation.objects.get(code=WAREHOUSE_SCRAP_CODE)
        self.material = Material.objects.create(
            code='DIS-01', name='DIS test', category=self.category, unit=self.unit,
        )
        StockBalance.objects.create(
            material=self.material, location=self.from_loc, quantity=Decimal('30'),
        )
        self.client.login(username='npl_dis', password='test')

    _seq = 0

    def _draft_disposal(self, qty=Decimal('8')):
        StockDisposalWorkflowTests._seq += 1
        disposal = StockDisposal.objects.create(
            number=f'PH-TEST-{StockDisposalWorkflowTests._seq:02d}',
            disposal_date=timezone.localdate(),
            from_location=self.from_loc,
            created_by=self.user,
        )
        StockDisposalLine.objects.create(
            disposal=disposal, material=self.material, quantity=qty,
        )
        return disposal

    def test_scrap_warehouse_seeded(self):
        self.assertEqual(self.scrap_loc.name, 'Kho hủy')

    def test_post_moves_stock_to_scrap_warehouse(self):
        disposal = self._draft_disposal(Decimal('8'))
        post_stock_disposal(disposal, self.user)
        disposal.refresh_from_db()
        self.assertEqual(disposal.status, DOC_STATUS_POSTED)

        from_bal = StockBalance.objects.get(material=self.material, location=self.from_loc)
        scrap_bal = StockBalance.objects.get(material=self.material, location=self.scrap_loc)
        self.assertEqual(from_bal.quantity, Decimal('22'))
        self.assertEqual(scrap_bal.quantity, Decimal('8'))

    def test_post_writes_ledger_both_locations(self):
        disposal = self._draft_disposal(Decimal('3'))
        post_stock_disposal(disposal, self.user)
        entries = StockLedger.objects.filter(
            ref_type=StockLedger.REF_DISPOSAL,
            ref_id=disposal.pk,
        )
        self.assertEqual(entries.count(), 2)
        self.assertTrue(entries.filter(location=self.from_loc, qty_delta=Decimal('-3')).exists())
        self.assertTrue(entries.filter(location=self.scrap_loc, qty_delta=Decimal('3')).exists())

    def test_disposal_pages_render(self):
        list_resp = self.client.get(reverse('kho_npl:disposal_list'))
        self.assertEqual(list_resp.status_code, 200)

        create_resp = self.client.get(reverse('kho_npl:disposal_create'))
        self.assertEqual(create_resp.status_code, 200)
        self.assertContains(create_resp, WAREHOUSE_SCRAP_CODE)
