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
