from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from hrm.models import PermissionGroup, Profile
from hrm.module_permissions import MODULE_KHO_NPL
from hrm.permissions import ROLE_EMPLOYEE
from kho_npl.choices import STOCK_STATUS_OUT
from kho_npl.models import Material, MaterialBatch, MaterialCategory, StockBalance, Unit, WarehouseLocation
from kho_npl.services.variant_groups import group_materials, group_stock_rows
from kho_npl.variant_group import infer_variant_group_from_code


class VariantGroupInferTests(TestCase):
    def test_infer_from_standard_codes(self):
        self.assertEqual(infer_variant_group_from_code('VAI-SIEU-01'), 'SIEU')
        self.assertEqual(infer_variant_group_from_code('VAI-CR3-04'), 'CR3')
        self.assertEqual(infer_variant_group_from_code('BB-BICH-01'), 'BICH')
        self.assertEqual(infer_variant_group_from_code('JP-NUT-01'), 'NUT')
        self.assertEqual(infer_variant_group_from_code('VAI-CASAU'), 'CASAU')
        self.assertEqual(infer_variant_group_from_code('VAI-MK11.2-04'), 'MK11.2')
        self.assertEqual(infer_variant_group_from_code('PK-AC'), 'AC')


class VariantGroupServiceTests(TestCase):
    def setUp(self):
        self.category = MaterialCategory.objects.get(code='vai-chinh')
        self.other_cat = MaterialCategory.objects.get(code='bao-bi')
        self.unit = Unit.objects.get(code='met')
        self.unit_kg = Unit.objects.filter(code='kg').first() or Unit.objects.create(
            code='kg', name='Kg', is_active=True,
        )
        self.location = WarehouseLocation.objects.get(code='MAIN')

    def test_group_same_variant_group(self):
        m1 = Material.objects.create(
            code='VAI-SIEU-01', name='SIEU DEN', category=self.category,
            unit=self.unit, variant_group='SIEU',
        )
        m2 = Material.objects.create(
            code='VAI-SIEU-02', name='SIEU TRANG', category=self.category,
            unit=self.unit, variant_group='SIEU',
        )
        groups = group_materials([m1, m2])
        self.assertEqual(len(groups), 1)
        self.assertTrue(groups[0]['can_expand'])
        self.assertEqual(groups[0]['variant_count'], 2)
        self.assertEqual(groups[0]['group_name'], 'VAI-SIEU')

    def test_do_not_group_different_category_or_unit(self):
        m1 = Material.objects.create(
            code='VAI-X-01', name='X1', category=self.category,
            unit=self.unit, variant_group='X',
        )
        m2 = Material.objects.create(
            code='BB-X-01', name='X2', category=self.other_cat,
            unit=self.unit, variant_group='X',
        )
        m3 = Material.objects.create(
            code='VAI-X-02', name='X3', category=self.category,
            unit=self.unit_kg, variant_group='X',
        )
        groups = group_materials([m1, m2, m3])
        self.assertEqual(len(groups), 3)
        self.assertFalse(any(g['can_expand'] for g in groups))

    def test_stock_group_totals_and_worst_status(self):
        m1 = Material.objects.create(
            code='VAI-Y-01', name='Y1', category=self.category,
            unit=self.unit, variant_group='Y', min_stock=Decimal('10'),
        )
        m2 = Material.objects.create(
            code='VAI-Y-02', name='Y2', category=self.category,
            unit=self.unit, variant_group='Y', min_stock=Decimal('5'),
        )
        StockBalance.objects.create(material=m1, location=self.location, quantity=Decimal('20'))
        StockBalance.objects.create(material=m2, location=self.location, quantity=Decimal('0'))
        MaterialBatch.objects.create(
            material=m1, code='L1', unit_price=Decimal('10000'), quantity=Decimal('20'),
        )
        MaterialBatch.objects.create(
            material=m2, code='L2', unit_price=Decimal('20000'), quantity=Decimal('0'),
        )
        from kho_npl.services.stock import material_stock_rows
        rows = material_stock_rows(Material.objects.filter(pk__in=[m1.pk, m2.pk]))
        groups = group_stock_rows(rows)
        self.assertEqual(len(groups), 1)
        g = groups[0]
        self.assertEqual(g['total_qty'], Decimal('20'))
        self.assertEqual(g['status'], STOCK_STATUS_OUT)
        self.assertEqual(g['stock_value'], Decimal('200000.00'))
        self.assertEqual(g['avg_unit_price'], Decimal('10000.00'))


class VariantGroupViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='npl_vg', password='test')
        Profile.objects.filter(user=self.user).update(role=ROLE_EMPLOYEE, is_employed=True)
        group = PermissionGroup.objects.create(
            name='NPL VG',
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
        self.client.login(username='npl_vg', password='test')
        Material.objects.create(
            code='VAI-Z-01', name='Z DEN', category=self.category,
            unit=self.unit, variant_group='Z',
        )
        Material.objects.create(
            code='VAI-Z-02', name='Z TRANG', category=self.category,
            unit=self.unit, variant_group='Z',
        )

    def test_material_list_shows_expandable_group(self):
        response = self.client.get(reverse('kho_npl:material_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'jp-npl-group-expandable')
        self.assertContains(response, 'jp-npl-variant-row')
        self.assertContains(response, 'VAI-Z-01')
        self.assertContains(response, 'VAI-Z-02')

    def test_material_list_search_by_code(self):
        response = self.client.get(reverse('kho_npl:material_list'), {'q': 'VAI-Z'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'VAI-Z-01')
        self.assertTrue(response.context['expand_search_hits'])

    def test_save_infers_variant_group(self):
        material = Material.objects.create(
            code='VAI-ABC-03', name='abc test', category=self.category, unit=self.unit,
        )
        material.refresh_from_db()
        self.assertEqual(material.variant_group, 'ABC')
        self.assertEqual(material.name, 'ABC TEST')
