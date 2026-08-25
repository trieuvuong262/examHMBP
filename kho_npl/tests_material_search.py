from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from hrm.models import PermissionGroup, Profile
from hrm.module_permissions import MODULE_KHO_NPL
from hrm.permissions import ROLE_EMPLOYEE
from kho_npl.models import Material, MaterialCategory, StockBalance, Unit, WarehouseLocation


class MaterialSearchReceiptTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='npl_search', password='test')
        Profile.objects.filter(user=self.user).update(role=ROLE_EMPLOYEE, is_employed=True)
        self.group = PermissionGroup.objects.create(
            name='NPL Search',
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
        self.main = WarehouseLocation.objects.get(code='MAIN')
        self.other = WarehouseLocation.objects.create(
            code='CL2', name='19 Chien Luoc 2', is_active=True,
        )
        self.client.login(username='npl_search', password='test')

    def _create_bich(self):
        material = Material.objects.create(
            code='BB-BICH-04',
            name='BICH HD TRONG',
            category=self.category,
            unit=self.unit,
            primary_location=self.other,
        )
        StockBalance.objects.create(
            material=material, location=self.main, quantity=Decimal('20'),
        )
        return material

    def test_receipt_search_shows_material_stocked_in_other_warehouse(self):
        material = self._create_bich()
        url = reverse('kho_npl:material_search')
        response = self.client.get(url, {
            'q': 'BICH HD TRONG',
            'location_id': self.other.pk,
        })
        self.assertEqual(response.status_code, 200)
        ids = [row['id'] for row in response.json()['results']]
        self.assertIn(material.pk, ids)

    def test_issue_search_hides_material_with_no_stock_at_location(self):
        material = self._create_bich()
        url = reverse('kho_npl:material_search')
        response = self.client.get(url, {
            'q': 'BICH HD TRONG',
            'location_id': self.other.pk,
            'in_stock_only': '1',
        })
        self.assertEqual(response.status_code, 200)
        ids = [row['id'] for row in response.json()['results']]
        self.assertNotIn(material.pk, ids)
