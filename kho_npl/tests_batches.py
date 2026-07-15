from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from hrm.models import PermissionGroup, Profile
from hrm.module_permissions import MODULE_KHO_NPL
from hrm.permissions import ROLE_EMPLOYEE
from kho_npl.choices import DOC_STATUS_DRAFT
from kho_npl.models import (
    Material,
    MaterialBatch,
    MaterialCategory,
    StockBalance,
    StockIssue,
    StockIssueLine,
    StockReceipt,
    StockReceiptLine,
    Unit,
    WarehouseLocation,
)
from kho_npl.services.batches import avg_cost, material_batch_totals
from kho_npl.services.issues import IssueWorkflowError, post_stock_issue
from kho_npl.services.receipts import ReceiptWorkflowError, post_stock_receipt


def _pdf(name='doc.pdf'):
    return SimpleUploadedFile(name, b'%PDF-1.4', content_type='application/pdf')


class MaterialBatchPriceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='npl_batch', password='test')
        Profile.objects.filter(user=self.user).update(role=ROLE_EMPLOYEE, is_employed=True)
        group = PermissionGroup.objects.create(
            name='NPL Batch',
            module_permissions={
                MODULE_KHO_NPL: {
                    'view': True, 'create': True, 'update': True,
                    'delete': True, 'export': True,
                },
            },
        )
        profile = Profile.objects.get(user=self.user)
        profile.permission_group = group
        profile.save(update_fields=['permission_group'])
        self.category = MaterialCategory.objects.get(code='vai-chinh')
        self.unit = Unit.objects.get(code='met')
        self.location = WarehouseLocation.objects.get(code='MAIN')
        self.material = Material.objects.create(
            code='BATCH-01',
            name='NPL batch test',
            category=self.category,
            unit=self.unit,
        )
        self.client.login(username='npl_batch', password='test')

    def _receipt(self, qty, price, batch_code, number):
        receipt = StockReceipt.objects.create(
            number=number,
            receipt_date=timezone.localdate(),
            created_by=self.user,
            attachment=_pdf(f'{number}.pdf'),
            status=DOC_STATUS_DRAFT,
        )
        StockReceiptLine.objects.create(
            receipt=receipt,
            material=self.material,
            location=self.location,
            received_qty=qty,
            batch_code=batch_code,
            unit_price=price,
        )
        return post_stock_receipt(receipt, self.user)

    def test_receipt_creates_batch_and_increases_qty(self):
        self._receipt(Decimal('10'), Decimal('20000'), 'LO-A', 'PN-B-01')
        batch = MaterialBatch.objects.get(material=self.material, code='LO-A')
        self.assertEqual(batch.unit_price, Decimal('20000'))
        self.assertEqual(batch.quantity, Decimal('10'))
        balance = StockBalance.objects.get(material=self.material, location=self.location)
        self.assertEqual(balance.quantity, Decimal('10'))

    def test_receipt_same_batch_rejects_different_price(self):
        self._receipt(Decimal('10'), Decimal('20000'), 'LO-A', 'PN-B-02')
        with self.assertRaises(ReceiptWorkflowError):
            self._receipt(Decimal('5'), Decimal('25000'), 'LO-A', 'PN-B-03')

    def test_weighted_average_after_two_receipts(self):
        self._receipt(Decimal('10'), Decimal('10000'), 'LO-A', 'PN-B-04')
        self._receipt(Decimal('10'), Decimal('30000'), 'LO-B', 'PN-B-05')
        _qty, value, avg = material_batch_totals(self.material)
        self.assertEqual(_qty, Decimal('20'))
        self.assertEqual(value, Decimal('400000.00'))
        self.assertEqual(avg, Decimal('20000.00'))
        self.assertEqual(avg_cost(self.material), Decimal('20000.00'))

    def test_issue_uses_batch_price_and_decreases_batch_qty(self):
        self._receipt(Decimal('10'), Decimal('15000'), 'LO-A', 'PN-B-06')
        batch = MaterialBatch.objects.get(code='LO-A', material=self.material)
        issue = StockIssue.objects.create(
            number='PX-B-01',
            issue_date=timezone.localdate(),
            created_by=self.user,
            attachment=_pdf('px.pdf'),
            status=DOC_STATUS_DRAFT,
        )
        line = StockIssueLine.objects.create(
            issue=issue,
            material=self.material,
            location=self.location,
            quantity=Decimal('4'),
            batch=batch,
        )
        post_stock_issue(issue, self.user)
        line.refresh_from_db()
        batch.refresh_from_db()
        self.assertEqual(line.unit_price, Decimal('15000'))
        self.assertEqual(batch.quantity, Decimal('6'))
        self.assertEqual(
            StockBalance.objects.get(material=self.material, location=self.location).quantity,
            Decimal('6'),
        )

    def test_issue_fails_when_batch_qty_insufficient(self):
        self._receipt(Decimal('3'), Decimal('10000'), 'LO-A', 'PN-B-07')
        batch = MaterialBatch.objects.get(code='LO-A', material=self.material)
        issue = StockIssue.objects.create(
            number='PX-B-02',
            issue_date=timezone.localdate(),
            created_by=self.user,
            attachment=_pdf('px2.pdf'),
            status=DOC_STATUS_DRAFT,
        )
        StockIssueLine.objects.create(
            issue=issue,
            material=self.material,
            location=self.location,
            quantity=Decimal('5'),
            batch=batch,
        )
        with self.assertRaises(IssueWorkflowError):
            post_stock_issue(issue, self.user)

    def test_batch_lookup_api(self):
        self._receipt(Decimal('8'), Decimal('11000'), 'LO-API', 'PN-B-08')
        url = reverse('kho_npl:batch_lookup') + f'?material_id={self.material.pk}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        results = response.json()['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['code'], 'LO-API')
        self.assertEqual(results[0]['unit_price'], '11000.00')
