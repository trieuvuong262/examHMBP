import io

import pandas as pd
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from hrm.models import PermissionGroup, Profile
from hrm.module_permissions import MODULE_KHO_NPL
from hrm.permissions import ROLE_EMPLOYEE
from kho_npl.forms import MaterialForm, StockReceiptLineForm
from kho_npl.models import Material, MaterialCategory, Unit, WarehouseLocation
from kho_npl.services.material_import_export import (
    EXCEL_HEADERS,
    import_materials_from_excel,
    material_to_row,
)
from kho_npl.services.scrap_warehouse import material_default_location


class MaterialPrimaryLocationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='npl_loc', password='test')
        Profile.objects.filter(user=self.user).update(role=ROLE_EMPLOYEE, is_employed=True)
        self.group = PermissionGroup.objects.create(
            name='NPL Location',
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
        self.main = WarehouseLocation.objects.get(code='MAIN')
        self.other = WarehouseLocation.objects.create(
            code='KE-A', name='Ke A', is_active=True,
        )
        self.client.login(username='npl_loc', password='test')

    def _xlsx(self, rows):
        df = pd.DataFrame(rows)
        buf = io.BytesIO()
        df.to_excel(buf, index=False)
        buf.seek(0)
        return buf

    def test_form_and_list_show_default_location(self):
        create = self.client.get(reverse('kho_npl:material_create'))
        self.assertEqual(create.status_code, 200)
        self.assertContains(create, 'primary_location')
        listing = self.client.get(reverse('kho_npl:material_list'))
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, 'data-col="primary_location"')

    def test_create_saves_primary_location(self):
        response = self.client.post(reverse('kho_npl:material_create'), {
            'code': 'LOC-01',
            'name': 'Vai ke A',
            'category': self.category.pk,
            'unit': self.unit.pk,
            'primary_location': self.other.pk,
            'min_stock': '0',
            'is_active': 'on',
        })
        self.assertEqual(response.status_code, 302)
        material = Material.objects.get(code='LOC-01')
        self.assertEqual(material.primary_location_id, self.other.pk)

    def test_import_sets_and_keeps_when_column_missing(self):
        buf = self._xlsx([{
            'Ma NPL': 'IMP-LOC-01',
            'Ten NPL': 'Import vi tri',
            'Ma nhom': 'vai-chinh',
            'Ma DVT': 'met',
            'Ma vi tri': 'KE-A',
        }])
        result = import_materials_from_excel(buf)
        self.assertEqual(result['created'], 1, result.get('errors'))
        material = Material.objects.get(code='IMP-LOC-01')
        self.assertEqual(material.primary_location_id, self.other.pk)
        self.assertEqual(material_to_row(material)['Mã vị trí'], 'KE-A')
        self.assertIn('Mã vị trí', EXCEL_HEADERS)

        buf2 = self._xlsx([{
            'Ma NPL': 'IMP-LOC-01',
            'Ten NPL': 'Import vi tri',
            'Ma nhom': 'vai-chinh',
            'Ma DVT': 'met',
        }])
        result2 = import_materials_from_excel(buf2)
        self.assertEqual(result2['updated'], 1, result2.get('errors'))
        material.refresh_from_db()
        self.assertEqual(material.primary_location_id, self.other.pk)

    def test_import_unknown_location_skips(self):
        buf = self._xlsx([{
            'Ma NPL': 'IMP-LOC-BAD',
            'Ten NPL': 'Sai vi tri',
            'Ma nhom': 'vai-chinh',
            'Ma DVT': 'met',
            'Ma vi tri': 'KHONG-CO',
        }])
        result = import_materials_from_excel(buf)
        self.assertEqual(result['created'], 0)
        self.assertEqual(result['skipped'], 1)
        self.assertTrue(result['errors'])
        self.assertFalse(Material.objects.filter(code='IMP-LOC-BAD').exists())

    def test_receipt_line_prefers_material_location(self):
        material = Material.objects.create(
            code='LOC-RCP',
            name='Vai nhap',
            category=self.category,
            unit=self.unit,
            primary_location=self.other,
        )
        form = StockReceiptLineForm(initial={'material': material.pk})
        self.assertEqual(form.initial.get('location'), self.other.pk)

    def test_material_default_location_fallback_main(self):
        material = Material.objects.create(
            code='LOC-NONE',
            name='Chua gan ke',
            category=self.category,
            unit=self.unit,
        )
        self.assertEqual(material_default_location(material).pk, self.main.pk)
        self.assertEqual(material_default_location(None).pk, self.main.pk)

    def test_new_form_defaults_to_main(self):
        form = MaterialForm()
        self.assertEqual(form.initial.get('primary_location'), self.main.pk)
