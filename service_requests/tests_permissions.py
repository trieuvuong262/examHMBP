from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from hrm.models import Department, DepartmentMenuPermission, PermissionGroup, Profile
from hrm.module_permissions import MODULE_DE_XUAT, MODULE_HO_TRO
from hrm.permissions import ROLE_EMPLOYEE
from hrm.group_permissions import normalize_group_permissions, permissions_from_legacy_role
from service_requests.models import RequestType


class ServiceRequestsGranularPermissionTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='SR Perm Dept', sort_order=1)
        DepartmentMenuPermission.objects.create(
            department=self.dept,
            modules=['de_xuat', 'ho_tro'],
        )

        base = normalize_group_permissions(permissions_from_legacy_role(ROLE_EMPLOYEE))

        de_xuat_view = dict(base)
        de_xuat_view[MODULE_DE_XUAT] = {
            'view': True, 'create': False, 'update': False, 'delete': False, 'export': False,
        }
        de_xuat_view[MODULE_HO_TRO] = {
            'view': False, 'create': False, 'update': False, 'delete': False, 'export': False,
        }
        self.group_de_xuat_view = PermissionGroup.objects.create(
            slug='test-de-xuat-view',
            name='De xuat view only',
            module_permissions=de_xuat_view,
        )

        ho_tro_create = dict(base)
        ho_tro_create[MODULE_DE_XUAT] = {
            'view': False, 'create': False, 'update': False, 'delete': False, 'export': False,
        }
        ho_tro_create[MODULE_HO_TRO] = {
            'view': True, 'create': True, 'update': False, 'delete': False, 'export': False,
        }
        self.group_ho_tro_create = PermissionGroup.objects.create(
            slug='test-ho-tro-create',
            name='Ho tro create',
            module_permissions=ho_tro_create,
        )

        self.de_xuat_view_user = self._user('dx_view', self.group_de_xuat_view)
        self.ho_tro_user = self._user('ht_create', self.group_ho_tro_create)

        RequestType.objects.get_or_create(
            code=RequestType.CODE_ASSET_PURCHASE,
            defaults={'name': 'Đề xuất mua tài sản', 'is_active': True},
        )
        RequestType.objects.get_or_create(
            code=RequestType.CODE_IT_REPAIR,
            defaults={'name': 'Hỗ trợ kỹ thuật', 'is_active': True},
        )

        self.client = Client(HTTP_HOST='testserver')

    def _user(self, username, group):
        user = User.objects.create_user(username=username, password='testpass123')
        Profile.objects.filter(user=user).update(
            department=self.dept,
            role=ROLE_EMPLOYEE,
            permission_group=group,
            is_employed=True,
        )
        user.refresh_from_db()
        return user

    def test_de_xuat_view_only_can_open_my_list(self):
        self.client.force_login(self.de_xuat_view_user)
        response = self.client.get(reverse('service_requests:de_xuat_my'))
        self.assertEqual(response.status_code, 200)

    def test_de_xuat_view_only_cannot_open_create(self):
        self.client.force_login(self.de_xuat_view_user)
        response = self.client.get(reverse('service_requests:create'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home_portal'))

    def test_ho_tro_create_user_can_open_it_repair_form(self):
        self.client.force_login(self.ho_tro_user)
        response = self.client.get(reverse('service_requests:create_it_repair'))
        self.assertEqual(response.status_code, 200)

    def test_ho_tro_only_user_cannot_open_de_xuat_list(self):
        self.client.force_login(self.ho_tro_user)
        response = self.client.get(reverse('service_requests:de_xuat_my'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home_portal'))
