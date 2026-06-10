from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from hrm.models import PermissionGroup, Profile
from hrm.module_permissions import MODULE_KHO_NPL
from hrm.permissions import ROLE_EMPLOYEE
from kho_npl.choices import DOC_STATUS_DRAFT, DOC_STATUS_POSTED
from kho_npl.choices import ISSUE_TYPE_PRODUCTION
from kho_npl.models import (
    Material,
    MaterialCategory,
    StockBalance,
    StockIssue,
    StockLedger,
    StockReceipt,
    Unit,
    WarehouseLocation,
)


class KhoNplCrudTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='npl_crud', password='test')
        Profile.objects.filter(user=self.user).update(role=ROLE_EMPLOYEE, is_employed=True)
        self.group = PermissionGroup.objects.create(
            name='NPL Full',
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
        profile = Profile.objects.get(user=self.user)
        profile.permission_group = self.group
        profile.save(update_fields=['permission_group'])

        self.category = MaterialCategory.objects.get(code='vai-chinh')
        self.unit = Unit.objects.get(code='met')
        self.location = WarehouseLocation.objects.get(code='MAIN')
        self.client.login(username='npl_crud', password='test')

    def test_material_create_and_detail(self):
        url = reverse('kho_npl:material_create')
        response = self.client.post(url, {
            'code': 'vai-test-01',
            'name': 'Vải test',
            'category': self.category.pk,
            'unit': self.unit.pk,
            'min_stock': '10',
            'is_active': 'on',
        })
        self.assertEqual(response.status_code, 302)
        material = Material.objects.get(code='VAI-TEST-01')
        detail = self.client.get(reverse('kho_npl:material_detail', args=[material.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, 'VAI-TEST-01')

    def test_receipt_post_updates_stock_and_ledger(self):
        material = Material.objects.create(
            code='NPL-RCP-01',
            name='Chỉ test',
            category=self.category,
            unit=self.unit,
            min_stock=Decimal('5'),
        )
        receipt = StockReceipt.objects.create(
            number='PN-TEST-0001',
            receipt_date=timezone.localdate(),
            created_by=self.user,
            status=DOC_STATUS_DRAFT,
        )
        receipt.lines.create(
            material=material,
            ordered_qty=Decimal('0'),
            received_qty=Decimal('25'),
            location=self.location,
        )
        response = self.client.post(reverse('kho_npl:receipt_post', args=[receipt.pk]))
        self.assertEqual(response.status_code, 302)
        receipt.refresh_from_db()
        self.assertEqual(receipt.status, DOC_STATUS_POSTED)
        balance = StockBalance.objects.get(material=material, location=self.location)
        self.assertEqual(balance.quantity, Decimal('25'))
        self.assertEqual(StockLedger.objects.filter(ref_number=receipt.number).count(), 1)

    def test_cannot_edit_posted_receipt(self):
        receipt = StockReceipt.objects.create(
            number='PN-TEST-0002',
            receipt_date=timezone.localdate(),
            created_by=self.user,
            status=DOC_STATUS_POSTED,
        )
        response = self.client.get(reverse('kho_npl:receipt_edit', args=[receipt.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('kho_npl:receipt_detail', args=[receipt.pk]))

    def test_issue_post_decreases_stock(self):
        material = Material.objects.create(
            code='NPL-ISS-01',
            name='Vải xuất test',
            category=self.category,
            unit=self.unit,
        )
        StockBalance.objects.create(material=material, location=self.location, quantity=Decimal('100'))
        issue = StockIssue.objects.create(
            number='PX-TEST-0001',
            issue_date=timezone.localdate(),
            issue_type=ISSUE_TYPE_PRODUCTION,
            created_by=self.user,
            status=DOC_STATUS_DRAFT,
        )
        issue.lines.create(material=material, quantity=Decimal('30'), location=self.location)
        response = self.client.post(reverse('kho_npl:issue_post', args=[issue.pk]))
        self.assertEqual(response.status_code, 302)
        issue.refresh_from_db()
        self.assertEqual(issue.status, DOC_STATUS_POSTED)
        balance = StockBalance.objects.get(material=material, location=self.location)
        self.assertEqual(balance.quantity, Decimal('70'))
        ledger = StockLedger.objects.get(ref_number=issue.number)
        self.assertEqual(ledger.qty_delta, Decimal('-30'))

    def test_issue_post_fails_when_insufficient_stock(self):
        material = Material.objects.create(
            code='NPL-ISS-02',
            name='Hết tồn test',
            category=self.category,
            unit=self.unit,
        )
        StockBalance.objects.create(material=material, location=self.location, quantity=Decimal('5'))
        issue = StockIssue.objects.create(
            number='PX-TEST-0002',
            issue_date=timezone.localdate(),
            created_by=self.user,
            status=DOC_STATUS_DRAFT,
        )
        issue.lines.create(material=material, quantity=Decimal('10'), location=self.location)
        self.client.post(reverse('kho_npl:issue_post', args=[issue.pk]))
        issue.refresh_from_db()
        self.assertEqual(issue.status, DOC_STATUS_DRAFT)
        balance = StockBalance.objects.get(material=material, location=self.location)
        self.assertEqual(balance.quantity, Decimal('5'))

    def test_settings_unit_create(self):
        response = self.client.post(
            reverse('kho_npl:settings_create', kwargs={'section': 'dvt'}),
            {'code': 'thung', 'name': 'Thùng', 'is_active': 'on'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Unit.objects.filter(code='thung', name='Thùng').exists())
