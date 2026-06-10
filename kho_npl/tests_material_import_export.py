import io

import pandas as pd
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from hrm.models import PermissionGroup, Profile
from hrm.module_permissions import MODULE_KHO_NPL
from hrm.permissions import ROLE_EMPLOYEE
from kho_npl.models import Material, MaterialCategory, Unit
from kho_npl.services.material_import_export import import_materials_from_excel


class MaterialImportExportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='npl_mat_io', password='test')
        Profile.objects.filter(user=self.user).update(role=ROLE_EMPLOYEE, is_employed=True)
        self.group = PermissionGroup.objects.create(
            name='NPL Material IO',
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
        self.client.login(username='npl_mat_io', password='test')

    def _xlsx_bytes(self, rows):
        df = pd.DataFrame(rows)
        buf = io.BytesIO()
        df.to_excel(buf, index=False)
        buf.seek(0)
        return buf

    def test_material_list_has_column_picker_and_io_buttons(self):
        response = self.client.get(reverse('kho_npl:material_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'npl-col-toggle')
        self.assertContains(response, 'bi-check2-square')
        self.assertContains(response, 'Xuất file')
        self.assertContains(response, 'Import')

    def test_export_returns_xlsx(self):
        Material.objects.create(
            code='EXP-01', name='Export test', category=self.category, unit=self.unit,
        )
        response = self.client.get(reverse('kho_npl:material_export'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            response['Content-Type'],
        )

    def test_import_creates_and_updates(self):
        buf = self._xlsx_bytes([{
            'Mã NPL': 'IMP-01',
            'Tên NPL': 'Import mới',
            'Mã nhóm': 'vai-chinh',
            'Mã ĐVT': 'met',
            'Tồn tối thiểu': 5,
            'Đang dùng': 'Có',
        }])
        result = import_materials_from_excel(buf)
        self.assertEqual(result['created'], 1)
        self.assertTrue(Material.objects.filter(code='IMP-01').exists())

        buf2 = self._xlsx_bytes([{
            'Mã NPL': 'IMP-01',
            'Tên NPL': 'Import cập nhật',
            'Mã nhóm': 'vai-chinh',
            'Mã ĐVT': 'met',
        }])
        result2 = import_materials_from_excel(buf2)
        self.assertEqual(result2['updated'], 1)
        self.assertEqual(Material.objects.get(code='IMP-01').name, 'Import cập nhật')

    def test_import_template_download(self):
        response = self.client.get(reverse('kho_npl:material_import_template'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('spreadsheet', response['Content-Type'])
