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

    def test_transfer_hub_default_tab_is_danh_sach(self):
        response = self.client.get(reverse('kho_npl:transfer_hub'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'jp-npl-transfer-search-form')
        self.assertContains(response, 'jp-npl-transfer-status-filters')

    def test_transfer_hub_tabs_render(self):
        self._draft_transfer()

        in_transit = self._draft_transfer()
        send_stock_transfer(in_transit, self.user)

        nhap = self.client.get(reverse('kho_npl:transfer_hub') + '?tab=nhap')
        self.assertEqual(nhap.status_code, 200)
        self.assertContains(nhap, 'Lưu phiếu')
        self.assertContains(nhap, 'jp-npl-material-select')
        self.assertContains(nhap, 'tim-npl')

        chuyen = self.client.get(reverse('kho_npl:transfer_hub') + '?tab=chuyen')
        self.assertEqual(chuyen.status_code, 200)
        self.assertContains(chuyen, 'Chuyển')

        nhan = self.client.get(reverse('kho_npl:transfer_hub') + '?tab=nhan')
        self.assertEqual(nhan.status_code, 200)
        self.assertContains(nhan, 'Xác nhận nhận')

        received = self._draft_transfer()
        send_stock_transfer(received, self.user)
        receive_stock_transfer(received, self.user)

        danh_sach = self.client.get(reverse('kho_npl:transfer_hub') + '?tab=danh-sach')
        self.assertEqual(danh_sach.status_code, 200)
        self.assertContains(danh_sach, 'jp-npl-transfer-status-filters')
        self.assertContains(danh_sach, 'Xem chi tiết')
        self.assertContains(danh_sach, 'Chưa nhận')

        filtered = self.client.get(
            reverse('kho_npl:transfer_hub') + '?tab=danh-sach&status=received',
        )
        self.assertEqual(filtered.status_code, 200)
        self.assertContains(filtered, 'Đã nhận')

    def test_transfer_create_redirects_to_chuyen_tab(self):
        url = reverse('kho_npl:transfer_create')
        get_resp = self.client.get(url)
        self.assertEqual(get_resp.status_code, 302)
        self.assertIn('tab=nhap', get_resp.url)

        response = self.client.post(url, {
            'transfer_date': timezone.localdate().isoformat(),
            'from_location': self.from_loc.pk,
            'to_location': self.to_loc.pk,
            'notes': '',
            'lines-TOTAL_FORMS': '1',
            'lines-INITIAL_FORMS': '0',
            'lines-MIN_NUM_FORMS': '0',
            'lines-MAX_NUM_FORMS': '1000',
            'lines-0-material': self.material.pk,
            'lines-0-quantity': '3',
            'lines-0-notes': '',
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('tab=chuyen', response.url)
        self.assertEqual(StockTransfer.objects.filter(status=TRANSFER_STATUS_DRAFT).count(), 1)

    def test_edit_transfer_rejects_warehouse_change_when_lines_exist(self):
        transfer = self._draft_transfer()
        url = reverse('kho_npl:transfer_edit', args=[transfer.pk])
        other_loc = WarehouseLocation.objects.create(code='ALT', name='Kho khác', is_active=True)
        response = self.client.post(url, {
            'transfer_date': timezone.localdate().isoformat(),
            'from_location': other_loc.pk,
            'to_location': self.to_loc.pk,
            'notes': '',
            'lines-TOTAL_FORMS': '1',
            'lines-INITIAL_FORMS': '1',
            'lines-MIN_NUM_FORMS': '0',
            'lines-MAX_NUM_FORMS': '1000',
            'lines-0-id': transfer.lines.first().pk,
            'lines-0-material': self.material.pk,
            'lines-0-quantity': '10',
            'lines-0-notes': '',
        })
        self.assertEqual(response.status_code, 302)
        transfer.refresh_from_db()
        self.assertEqual(transfer.from_location_id, self.from_loc.pk)

    def test_material_search_api(self):
        url = reverse('kho_npl:material_search') + '?q=XF'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(any(r['code'] == 'XF-01' for r in data['results']))

    def test_overview_has_no_module_tab_pills(self):
        response = self.client.get(reverse('kho_npl:overview'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'jp-tab-pills')
