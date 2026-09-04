import io
import unittest

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from hrm.models import Department, DepartmentMenuPermission, Profile
from hrm.module_permissions import HIDDEN_PORTAL_MODULES, MODULE_KPI
from hrm.permissions import ROLE_EMPLOYEE, ROLE_TEAM_LEADER
from kpi.models import MonthlyKpi, MonthlyKpiItem
from kpi.services.monthly_import import build_monthly_kpi_sample_xlsx, parse_monthly_kpi_workbook

skip_if_kpi_hidden = unittest.skipUnless(
    MODULE_KPI not in HIDDEN_PORTAL_MODULES,
    'KPI module is temporarily hidden from portal',
)


def _profile(user, **kwargs):
    profile, _ = Profile.objects.get_or_create(user=user)
    for key, value in kwargs.items():
        setattr(profile, key, value)
    profile.save()
    return profile


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
@skip_if_kpi_hidden
class MonthlyKpiAccessTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='KPI Test Dept')
        DepartmentMenuPermission.objects.create(department=self.dept, modules=['kpi'])
        now = timezone.localdate()
        self.year, self.month = now.year, now.month

        self.employee = User.objects.create_user(username='kpi_emp', password='pass12345')
        _profile(self.employee, full_name='Employee', department=self.dept, role=ROLE_EMPLOYEE, is_employed=True)

        self.other = User.objects.create_user(username='kpi_other', password='pass12345')
        _profile(self.other, full_name='Other', department=self.dept, role=ROLE_EMPLOYEE, is_employed=True)

        self.manager = User.objects.create_user(username='kpi_mgr', password='pass12345')
        _profile(self.manager, full_name='Manager', department=self.dept, role=ROLE_TEAM_LEADER, is_employed=True)
        self.manager.profile.subordinates.add(self.employee)

        self.board = MonthlyKpi.objects.create(
            employee=self.employee,
            direct_manager=self.manager,
            year=self.year,
            month=self.month,
        )
        MonthlyKpiItem.objects.create(
            monthly_kpi=self.board,
            sort_order=1,
            work_group='Nhom A',
            weightage=100,
            indicator='Tieu chi 1',
        )
        self.client = Client(HTTP_HOST='testserver')

    def test_other_employee_cannot_view_kpi_detail(self):
        self.client.login(username='kpi_other', password='pass12345')
        url = reverse('kpi_detail', kwargs={'kpi_id': self.board.id})
        response = self.client.get(url)
        self.assertRedirects(response, reverse('kpi_list'))

    def test_manager_can_view_team_kpi_detail(self):
        self.client.login(username='kpi_mgr', password='pass12345')
        url = reverse('kpi_detail', kwargs={'kpi_id': self.board.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_employee_can_save_self_score(self):
        self.client.login(username='kpi_emp', password='pass12345')
        item = self.board.items.get()
        response = self.client.post(reverse('kpi_detail', kwargs={'kpi_id': self.board.id}), {
            f'item_{item.id}_self_actual': 'Hoan thanh 100%',
            f'item_{item.id}_self_score': '10',
        })
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.self_score, 10.0)
        self.assertIn('Hoan thanh', item.self_actual)

    def test_employee_cannot_save_manager_score(self):
        self.client.login(username='kpi_emp', password='pass12345')
        item = self.board.items.get()
        self.client.post(reverse('kpi_detail', kwargs={'kpi_id': self.board.id}), {
            f'item_{item.id}_self_score': '9',
            f'item_{item.id}_mgr_score': '12',
            f'item_{item.id}_mgr_actual': 'hack',
        })
        item.refresh_from_db()
        self.assertEqual(item.self_score, 9.0)
        self.assertIsNone(item.mgr_score)
        self.assertEqual(item.mgr_actual, '')


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
@skip_if_kpi_hidden
class MonthlyKpiScoreTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='kpi_score', password='x')
        self.board = MonthlyKpi.objects.create(
            employee=self.user,
            year=2026,
            month=8,
        )
        MonthlyKpiItem.objects.create(
            monthly_kpi=self.board, sort_order=1, weightage=50, indicator='A', self_score=8,
        )
        MonthlyKpiItem.objects.create(
            monthly_kpi=self.board, sort_order=2, weightage=50, indicator='B', self_score=10, mgr_score=12,
        )

    def test_total_prefers_manager_score(self):
        self.assertEqual(self.board.total_score(), 100.0)
        self.assertEqual(self.board.result_code(), MonthlyKpi.RESULT_PASS)

    def test_result_exceed(self):
        item = self.board.items.get(sort_order=1)
        item.mgr_score = 12
        item.save()
        self.assertEqual(self.board.total_score(), 120.0)
        self.assertEqual(self.board.result_code(), MonthlyKpi.RESULT_EXCEED)


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
@skip_if_kpi_hidden
class MonthlyKpiImportTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='KPI Import Dept', sort_order=2)
        DepartmentMenuPermission.objects.create(department=self.dept, modules=['kpi'])
        self.employee = User.objects.create_user(username='kpi_imp_emp', password='pass12345')
        _profile(self.employee, full_name='NV Import', department=self.dept, role=ROLE_EMPLOYEE, is_employed=True)
        self.manager = User.objects.create_user(username='kpi_imp_mgr', password='pass12345')
        _profile(self.manager, full_name='Mgr Import', department=self.dept, role=ROLE_TEAM_LEADER, is_employed=True)
        self.manager.profile.subordinates.add(self.employee)
        self.client = Client(HTTP_HOST='testserver')
        self.client.login(username='kpi_imp_mgr', password='pass12345')

    def test_parse_sample_workbook(self):
        raw = build_monthly_kpi_sample_xlsx()
        parsed = parse_monthly_kpi_workbook(io.BytesIO(raw))
        self.assertGreaterEqual(len(parsed.rows), 2)
        self.assertTrue(parsed.rows[0].indicator)

    def test_import_creates_monthly_board(self):
        now = timezone.localdate()
        raw = build_monthly_kpi_sample_xlsx()
        upload = SimpleUploadedFile(
            'kpi.xlsx',
            raw,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response = self.client.post(reverse('kpi_import_excel'), {
            'employee_id': self.employee.pk,
            'year': str(now.year),
            'month': str(now.month),
            'excel_file': upload,
        })
        self.assertEqual(response.status_code, 302)
        board = MonthlyKpi.objects.get(employee=self.employee, year=now.year, month=now.month)
        self.assertGreaterEqual(board.items.count(), 2)
        self.assertEqual(board.direct_manager_id, self.manager.pk)

    def test_list_filter_by_month(self):
        MonthlyKpi.objects.create(employee=self.employee, direct_manager=self.manager, year=2026, month=1)
        MonthlyKpi.objects.create(employee=self.employee, direct_manager=self.manager, year=2026, month=8)
        response = self.client.get(reverse('kpi_list'), {'year': 2026, 'month': 8})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '08/2026')
        self.assertNotContains(response, '01/2026')

