from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from hrm.models import PermissionGroup, Profile
from hrm.module_permissions import MODULE_KHO_NPL
from hrm.permissions import ROLE_EMPLOYEE
from kho_npl.models import MaterialSpecification, Unit


class SpecQuickAddReturnTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='npl_spec_next', password='test')
        Profile.objects.filter(user=self.user).update(role=ROLE_EMPLOYEE, is_employed=True)
        group = PermissionGroup.objects.create(
            name='NPL Spec Next',
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
        profile.permission_group = group
        profile.save(update_fields=['permission_group'])
        self.unit = Unit.objects.get(code='met')
        self.client.login(username='npl_spec_next', password='test')
        self.create_url = reverse('kho_npl:material_create')
        self.spec_create_url = reverse('kho_npl:settings_create', kwargs={'section': 'quy-cach'})

    def test_material_form_links_spec_create_with_next(self):
        response = self.client.get(self.create_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'{self.spec_create_url}?next={self.create_url}')
        href_block = response.content.decode()
        spec_idx = href_block.find('Thêm quy cách')
        self.assertGreater(spec_idx, 0)
        nearby = href_block[max(0, spec_idx - 400):spec_idx]
        self.assertNotIn('target="_blank"', nearby)

    def test_create_spec_with_next_returns_to_material_form(self):
        response = self.client.post(self.spec_create_url, {
            'code': 'qc-quick-add-01',
            'name': 'Quy cach quick add',
            'level1_unit': self.unit.pk,
            'sort_order': '0',
            'is_active': 'on',
            'next': self.create_url,
        })
        self.assertEqual(response.status_code, 302)
        spec = MaterialSpecification.objects.get(code='qc-quick-add-01')
        self.assertEqual(
            response.url,
            f'{self.create_url}?select_specification={spec.pk}',
        )

    def test_create_spec_without_next_stays_on_settings_list(self):
        response = self.client.post(self.spec_create_url, {
            'code': 'qc-quick-add-02',
            'name': 'Quy cach list',
            'level1_unit': self.unit.pk,
            'sort_order': '0',
            'is_active': 'on',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse('kho_npl:settings_list', kwargs={'section': 'quy-cach'}),
        )

    def test_rejects_external_next(self):
        response = self.client.post(self.spec_create_url, {
            'code': 'qc-quick-add-03',
            'name': 'Quy cach unsafe next',
            'level1_unit': self.unit.pk,
            'sort_order': '0',
            'is_active': 'on',
            'next': 'https://example.com/phishing',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse('kho_npl:settings_list', kwargs={'section': 'quy-cach'}),
        )

    def test_material_form_preselects_new_specification(self):
        spec = MaterialSpecification.objects.create(
            code='qc-quick-add-04',
            name='Quy cach preselect',
        )
        spec.levels.create(level=1, unit=self.unit, qty_in_next_lower=1)
        response = self.client.get(self.create_url, {'select_specification': spec.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'<option value="{spec.pk}" selected',
            html=False,
        )
