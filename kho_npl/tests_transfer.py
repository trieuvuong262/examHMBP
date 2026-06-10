from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from hrm.models import PermissionGroup, Profile
from hrm.module_permissions import MODULE_KHO_NPL
from hrm.permissions import ROLE_EMPLOYEE
from kho_npl.choices import (
    TRANSFER_STATUS_DRAFT,
    TRANSFER_STATUS_IN_TRANSIT,
    TRANSFER_STATUS_RECEIVED,
)
from kho_npl.models import (
    Material,
    MaterialCategory,
    StockBalance,
    StockLedger,
    StockTransfer,
    StockTransferLine,
    Unit,
    WarehouseLocation,
)
from kho_npl.services.transfers import receive_stock_transfer, send_stock_transfer


class StockTransferWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='npl_xfer', password='test')
        Profile.objects.filter(user=self.user).update(role=ROLE_EMPLOYEE, is_employed=True)
        self.group = PermissionGroup.objects.create(
            name='NPL Transfer',
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
        self.to_loc = WarehouseLocation.objects.create(code='SUB', name='Kho phụ', is_active=True)
        self.material = Material.objects.create(
            code='XF-01', name='XF test', category=self.category, unit=self.unit,
        )
        StockBalance.objects.create(
            material=self.material, location=self.from_loc, quantity=Decimal('100'),
        )
        self.client.login(username='npl_xfer', password='test')

    _xfer_seq = 0

    def _draft_transfer(self, qty=Decimal('10'), *, number=None):
        StockTransferWorkflowTests._xfer_seq += 1
        if number is None:
            number = f'PC-TEST-{StockTransferWorkflowTests._xfer_seq:02d}'
        transfer = StockTransfer.objects.create(
            number=number,
            transfer_date=timezone.localdate(),
            from_location=self.from_loc,
            to_location=self.to_loc,
            created_by=self.user,
            status=TRANSFER_STATUS_DRAFT,
        )
        StockTransferLine.objects.create(
            transfer=transfer, material=self.material, quantity=qty,
        )
        return transfer

    def test_send_receive_updates_both_locations(self):
        transfer = self._draft_transfer(Decimal('15'))
        send_stock_transfer(transfer, self.user)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, TRANSFER_STATUS_IN_TRANSIT)

        from_bal = StockBalance.objects.get(material=self.material, location=self.from_loc)
        self.assertEqual(from_bal.quantity, Decimal('85'))

        receive_stock_transfer(transfer, self.user)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, TRANSFER_STATUS_RECEIVED)

        to_bal = StockBalance.objects.get(material=self.material, location=self.to_loc)
        self.assertEqual(to_bal.quantity, Decimal('15'))

    def test_send_creates_ledger_at_source(self):
        transfer = self._draft_transfer(Decimal('5'))
        send_stock_transfer(transfer, self.user)
        ledger = StockLedger.objects.filter(
            ref_type=StockLedger.REF_TRANSFER,
            ref_id=transfer.pk,
            location=self.from_loc,
        ).first()
        self.assertIsNotNone(ledger)
        self.assertEqual(ledger.qty_delta, Decimal('-5'))

    def test_transfer_hub_tabs_render(self):
        received = self._draft_transfer()
        send_stock_transfer(received, self.user)
        receive_stock_transfer(received, self.user)

        self._draft_transfer()

        in_transit = self._draft_transfer()
        send_stock_transfer(in_transit, self.user)

        for tab in ('nhap', 'chuyen', 'nhan'):
            url = reverse('kho_npl:transfer_hub') + f'?tab={tab}'
            with self.subTest(tab=tab):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'jp-npl-transfer-tabs')

    def test_overview_has_no_module_tab_pills(self):
        response = self.client.get(reverse('kho_npl:overview'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'jp-tab-pills')
