from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from hrm.models import PermissionGroup, Profile
from hrm.module_permissions import MODULE_KHO_NPL
from hrm.permissions import ROLE_EMPLOYEE
from kho_npl.models import (
    Material,
    MaterialCategory,
    StockIssue,
    StockIssueLine,
    StockReceipt,
    StockReceiptLine,
    Unit,
    WarehouseLocation,
)
from kho_npl.services.issues import post_stock_issue
from kho_npl.services.receipts import post_stock_receipt
from kho_npl.services.stock import material_total_qty
from kho_npl.models import StockBalance
from kho_npl.services.stock_card import (
    build_material_stock_card,
    diagnose_stock_mismatch,
    ledger_matches_stock,
)


class StockCardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='sc_user', password='test')
        Profile.objects.filter(user=self.user).update(role=ROLE_EMPLOYEE, is_employed=True)
        PermissionGroup.objects.create(
            name='SC',
            module_permissions={
                MODULE_KHO_NPL: {
                    'view': True, 'create': True, 'update': True,
                    'delete': True, 'export': True,
                },
            },
        )
        profile = Profile.objects.get(user=self.user)
        profile.permission_group = PermissionGroup.objects.get(name='SC')
        profile.save(update_fields=['permission_group'])

        self.category = MaterialCategory.objects.get(code='vai-chinh')
        self.unit = Unit.objects.get(code='met')
        self.location = WarehouseLocation.objects.get(code='MAIN')
        self.material = Material.objects.create(
            code='SC-TEST-01',
            name='Vải thẻ kho test',
            category=self.category,
            unit=self.unit,
        )
        self.client.login(username='sc_user', password='test')

    def _post_receipt(self, qty, number='PN-SC-01', batch_code=None, unit_price=None):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from decimal import Decimal
        receipt = StockReceipt.objects.create(
            number=number,
            receipt_date=timezone.localdate(),
            created_by=self.user,
            attachment=SimpleUploadedFile('pn.pdf', b'%PDF-1.4', content_type='application/pdf'),
        )
        StockReceiptLine.objects.create(
            receipt=receipt,
            material=self.material,
            location=self.location,
            ordered_qty=qty,
            received_qty=qty,
            batch_code=batch_code or number,
            unit_price=unit_price if unit_price is not None else Decimal('10000'),
        )
        post_stock_receipt(receipt, self.user)

    def _post_issue(self, qty, number='PX-SC-01'):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from kho_npl.models import MaterialBatch
        batch = MaterialBatch.objects.filter(material=self.material, quantity__gt=0).order_by('id').first()
        issue = StockIssue.objects.create(
            number=number,
            issue_date=timezone.localdate(),
            created_by=self.user,
            attachment=SimpleUploadedFile('px.pdf', b'%PDF-1.4', content_type='application/pdf'),
        )
        StockIssueLine.objects.create(
            issue=issue,
            material=self.material,
            location=self.location,
            quantity=qty,
            batch=batch,
        )
        post_stock_issue(issue, self.user)

    def test_stock_card_running_balance_matches_system(self):
        self._post_receipt(Decimal('100'))
        self._post_issue(Decimal('5'))
        self._post_receipt(Decimal('3'), number='PN-SC-02')

        card = build_material_stock_card(self.material)
        self.assertTrue(card['is_consistent'])
        self.assertEqual(material_total_qty(self.material), Decimal('98'))
        self.assertEqual(card['closing_balance'], Decimal('98'))
        self.assertEqual(card['scope_label'], 'Tổng kho chứa')
        self.assertFalse(card['scope_is_location'])

        txn_rows = [r for r in card['rows'] if r['kind'] == 'txn']
        self.assertEqual(len(txn_rows), 3)
        # Thẻ kho hiển thị phiếu mới nhất trước
        self.assertEqual(txn_rows[0]['qty_in'], Decimal('3'))
        self.assertEqual(txn_rows[0]['balance_after'], Decimal('98'))
        self.assertEqual(txn_rows[1]['qty_out'], Decimal('5'))
        self.assertEqual(txn_rows[1]['balance_after'], Decimal('95'))
        self.assertEqual(txn_rows[2]['qty_in'], Decimal('100'))
        self.assertEqual(txn_rows[2]['balance_after'], Decimal('100'))

    def test_diagnose_finds_location_mismatch(self):
        self._post_receipt(Decimal('10'))
        StockBalance.objects.filter(material=self.material, location=self.location).update(
            quantity=Decimal('999'),
        )
        diag = diagnose_stock_mismatch(self.material)
        self.assertEqual(diag['problem_count'], 1)
        self.assertEqual(diag['problem_rows'][0]['location_code'], self.location.display_label())
        self.assertEqual(diag['problem_rows'][0]['variance_ledger'], Decimal('989'))

    def test_stock_card_page_shows_diagnose_button_when_mismatch(self):
        self._post_receipt(Decimal('10'))
        StockBalance.objects.filter(material=self.material, location=self.location).update(
            quantity=Decimal('999'),
        )
        url = reverse('kho_npl:stock_cards') + f'?material={self.material.pk}&diagnose=1'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Kiểm tra lệch')
        self.assertContains(response, 'jp-npl-diagnose-table')
        self.assertContains(response, self.location.display_label())

    def test_stock_card_location_scope(self):
        self._post_receipt(Decimal('10'))
        card = build_material_stock_card(self.material, location_id=self.location.id)
        self.assertTrue(card['scope_is_location'])
        self.assertEqual(card['scope_label'], self.location.display_label())
        self.assertEqual(card['closing_balance'], Decimal('10'))

    def test_stock_card_multi_location_scope(self):
        loc_b = WarehouseLocation.objects.create(code='SC-B2', name='Kệ B2 test', is_active=True)
        self._post_receipt(Decimal('10'))
        receipt = StockReceipt.objects.create(
            number='PN-SC-MULTI',
            receipt_date=timezone.localdate(),
            created_by=self.user,
        )
        from django.core.files.uploadedfile import SimpleUploadedFile
        receipt.attachment = SimpleUploadedFile('pn2.pdf', b'%PDF-1.4', content_type='application/pdf')
        receipt.save(update_fields=['attachment'])
        StockReceiptLine.objects.create(
            receipt=receipt,
            material=self.material,
            location=loc_b,
            ordered_qty=Decimal('7'),
            received_qty=Decimal('7'),
            batch_code='PN-SC-MULTI',
            unit_price=Decimal('10000'),
        )
        post_stock_receipt(receipt, self.user)

        card = build_material_stock_card(
            self.material,
            location_ids=[self.location.id, loc_b.id],
        )
        self.assertTrue(card['scope_is_location'])
        self.assertEqual(card['system_stock'], Decimal('17'))
        self.assertEqual(card['ledger_total'], Decimal('17'))
        self.assertTrue(card['is_consistent'])

    def test_stock_card_page_loads(self):
        self._post_receipt(Decimal('10'))
        url = reverse('kho_npl:stock_cards') + f'?material={self.material.pk}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'SC-TEST-01')
        self.assertContains(response, 'PN-SC-01')
        self.assertTrue(ledger_matches_stock(self.material))
