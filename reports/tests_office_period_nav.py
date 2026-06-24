from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.permissions import ROLE_EMPLOYEE
from reports.period_utils import period_nav_date, PERIOD_DAY, PERIOD_MONTH, PERIOD_WEEK
from reports.report_profile import REPORT_PROFILE_OFFICE
from reports.week_utils import monday_of


class OfficePeriodNavTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(name='VP Nav Dept', sort_order=1)
        DepartmentMenuPermission.objects.create(department=dept, modules=['reports'])
        RoleModulePermission.objects.update_or_create(
            role=ROLE_EMPLOYEE,
            defaults={'module_permissions': {'reports': {'view': True, 'edit': True}}},
        )
        self.user = User.objects.create_user(username='vp_nav', password='test')
        Profile.objects.filter(user=self.user).update(
            department=dept,
            role=ROLE_EMPLOYEE,
            full_name='vp_nav',
            is_employed=True,
        )
        self.client = Client()

    def test_period_nav_date_uses_today_inside_current_week(self):
        today = date(2026, 6, 3)
        week_start = monday_of(today)
        class Req:
            GET = {}
        with patch('reports.period_utils.timezone.localdate', return_value=today):
            self.assertEqual(period_nav_date(Req(), PERIOD_WEEK, week_start), today)

    def test_period_nav_date_uses_today_inside_current_month(self):
        today = date(2026, 6, 15)
        month_start = date(2026, 6, 1)
        class Req:
            GET = {}
        with patch('reports.period_utils.timezone.localdate', return_value=today):
            self.assertEqual(period_nav_date(Req(), PERIOD_MONTH, month_start), today)

    def test_period_nav_date_respects_explicit_date(self):
        explicit = date(2026, 1, 10)
        class Req:
            GET = {'date': '2026-01-10'}
        with patch('reports.period_utils.timezone.localdate', return_value=date(2026, 6, 3)):
            self.assertEqual(
                period_nav_date(Req(), PERIOD_DAY, date(2026, 1, 10)),
                explicit,
            )

    def test_period_nav_date_ignores_week_anchor_in_query(self):
        today = date(2026, 6, 3)
        week_start = monday_of(today)
        class Req:
            GET = {'date': week_start.isoformat()}
        with patch('reports.period_utils.timezone.localdate', return_value=today):
            self.assertEqual(period_nav_date(Req(), PERIOD_WEEK, week_start), today)

    def test_vp_tabs_keep_today_when_switching_from_week(self):
        today = date(2026, 6, 3)
        week_start = monday_of(today)
        self.client.force_login(self.user)
        with patch('reports.period_utils.timezone.localdate', return_value=today), patch(
            'reports.report_lock.timezone.localdate',
            return_value=today,
        ):
            resp = self.client.get(
                reverse('reports:today_vp'),
                {'period': 'week', 'date': week_start.isoformat()},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f'period=day&date={today.isoformat()}')
        self.assertNotContains(resp, f'period=day&date={week_start.isoformat()}')
        self.assertNotContains(resp, 'Đã quá hạn chỉnh sửa')

    def test_vp_tabs_keep_today_when_switching_from_month(self):
        today = date(2026, 6, 3)
        self.client.force_login(self.user)
        with patch('reports.period_utils.timezone.localdate', return_value=today), patch(
            'reports.report_lock.timezone.localdate',
            return_value=today,
        ):
            resp = self.client.get(
                reverse('reports:today_vp'),
                {'period': 'month', 'month': '2026-06'},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f'period=day&date={today.isoformat()}')
        self.assertNotContains(resp, 'Đã quá hạn chỉnh sửa')
