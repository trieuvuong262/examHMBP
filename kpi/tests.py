from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from hrm.models import Department, DepartmentMenuPermission, Profile
from hrm.permissions import ROLE_EMPLOYEE, ROLE_TEAM_LEADER
from kpi.models import KpiPeriod, YearlyKpi


class KpiDetailAccessTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='KPI Test Dept')
        DepartmentMenuPermission.objects.create(
            department=self.dept,
            modules=['kpi'],
        )
        self.employee = User.objects.create_user(username='kpi_emp', password='pass12345')
        emp_profile, _ = Profile.objects.get_or_create(user=self.employee)
        emp_profile.full_name = 'Employee'
        emp_profile.department = self.dept
        emp_profile.role = ROLE_EMPLOYEE
        emp_profile.save()

        self.other = User.objects.create_user(username='kpi_other', password='pass12345')
        other_profile, _ = Profile.objects.get_or_create(user=self.other)
        other_profile.full_name = 'Other'
        other_profile.department = self.dept
        other_profile.role = ROLE_EMPLOYEE
        other_profile.save()

        self.manager = User.objects.create_user(username='kpi_mgr', password='pass12345')
        mgr_profile, _ = Profile.objects.get_or_create(user=self.manager)
        mgr_profile.full_name = 'Manager'
        mgr_profile.department = self.dept
        mgr_profile.role = ROLE_TEAM_LEADER
        mgr_profile.save()

        self.board = YearlyKpi.objects.create(
            employee=self.employee,
            direct_manager=self.manager,
            year=2026,
            eval_type='QUARTER',
        )
        KpiPeriod.objects.create(year=2026, period_type='Q1', title='Q1', is_active=True)

        self.client = Client()
        self.client.login(username='kpi_other', password='pass12345')

    def test_other_employee_cannot_view_kpi_detail(self):
        url = reverse('kpi_detail', kwargs={'kpi_id': self.board.id})
        response = self.client.get(url)
        self.assertRedirects(response, reverse('kpi_list'))

    def test_manager_can_view_team_kpi_detail(self):
        self.client.logout()
        self.client.login(username='kpi_mgr', password='pass12345')
        url = reverse('kpi_detail', kwargs={'kpi_id': self.board.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class KpiGranularPermissionTests(TestCase):
    def setUp(self):
        from hrm.models import PermissionGroup
        from hrm.module_permissions import MODULE_KPI
        from hrm.group_permissions import normalize_group_permissions, permissions_from_legacy_role

        self.dept = Department.objects.create(name='KPI Granular Dept', sort_order=2)
        DepartmentMenuPermission.objects.create(
            department=self.dept,
            modules=['kpi'],
        )

        base = normalize_group_permissions(permissions_from_legacy_role(ROLE_EMPLOYEE))
        view_only = dict(base)
        view_only[MODULE_KPI] = {
            'view': True,
            'create': False,
            'update': False,
            'delete': False,
            'export': False,
        }
        self.group_view = PermissionGroup.objects.create(
            slug='test-kpi-view',
            name='KPI view only',
            module_permissions=view_only,
        )

        create_group = dict(base)
        create_group[MODULE_KPI] = {
            'view': True,
            'create': True,
            'update': True,
            'delete': False,
            'export': False,
        }
        self.group_create = PermissionGroup.objects.create(
            slug='test-kpi-create',
            name='KPI create',
            module_permissions=create_group,
        )

        self.employee = User.objects.create_user(username='kpi_view_only', password='pass12345')
        Profile.objects.filter(user=self.employee).update(
            full_name='KPI View',
            department=self.dept,
            role=ROLE_EMPLOYEE,
            permission_group=self.group_view,
        )

        self.manager = User.objects.create_user(username='kpi_create_mgr', password='pass12345')
        Profile.objects.filter(user=self.manager).update(
            full_name='KPI Manager',
            department=self.dept,
            role=ROLE_TEAM_LEADER,
            permission_group=self.group_create,
        )

        self.client = Client(HTTP_HOST='testserver')

    def test_view_only_employee_cannot_open_yearly_create(self):
        self.client.force_login(self.employee)
        response = self.client.get(reverse('yearly_kpi_create'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home_portal'))

    def test_manager_with_create_perm_can_open_yearly_create(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse('yearly_kpi_create'))
        self.assertEqual(response.status_code, 200)
