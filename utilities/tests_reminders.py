from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from assessment.portal_widgets import get_portal_dashboard
from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.module_permissions import MODULE_UTILITIES
from hrm.permissions import ROLE_EMPLOYEE
from reports.report_profile import REPORT_PROFILE_OFFICE, REPORT_PROFILE_PRODUCTION
from utilities.meal_rules import meal_order_window_for
from utilities.models import MealOrderDecline, SalaryAdvanceDecline
from utilities.reminders import get_utilities_portal_widgets, get_utilities_pending_count


class UtilitiesReminderTests(TestCase):
    def setUp(self):
        self.prod_dept = Department.objects.create(
            name='SX Remind',
            sort_order=1,
            report_profile=REPORT_PROFILE_PRODUCTION,
        )
        self.office_dept = Department.objects.create(
            name='VP Remind',
            sort_order=2,
            report_profile=REPORT_PROFILE_OFFICE,
        )
        for dept in (self.prod_dept, self.office_dept):
            DepartmentMenuPermission.objects.create(department=dept, modules=['utilities'])
        RoleModulePermission.objects.update_or_create(
            role=ROLE_EMPLOYEE,
            defaults={
                'module_permissions': {
                    'utilities': {'view': True, 'edit': True},
                },
            },
        )
        self.prod_user = self._user('sx_remind', self.prod_dept)
        self.office_user = self._user('vp_remind', self.office_dept)
        self.client = Client(HTTP_HOST='testserver')

    def _user(self, username, dept):
        user = User.objects.create_user(username=username, password='test')
        Profile.objects.filter(user=user).update(
            department=dept,
            role=ROLE_EMPLOYEE,
            full_name=username,
            is_employed=True,
        )
        user.refresh_from_db()
        return user

    def _meal_window_now(self, *, order_day=None):
        """Trả về (now, meal_date) trong khung 16h–20h; mặc định tránh ngày 18–19 (ứng lương)."""
        if order_day is None:
            today = timezone.localdate()
            if today.day in (18, 19):
                order_day = today.replace(day=10)
            else:
                order_day = today
        meal_date = order_day + timedelta(days=1)
        start, _ = meal_order_window_for(meal_date)
        now = start + timedelta(minutes=5)
        return now, meal_date

    @override_settings(USE_TZ=True)
    def test_meal_reminder_only_production_during_window(self):
        now, _ = self._meal_window_now()
        with patch('django.utils.timezone.localtime', return_value=now):
            widgets = get_utilities_portal_widgets(self.prod_user)
            self.assertEqual(len(widgets), 1)
            self.assertEqual(widgets[0]['title'], 'Đặt cơm công ty')
            self.assertEqual(len(get_utilities_portal_widgets(self.office_user)), 0)

    @override_settings(USE_TZ=True)
    def test_meal_decline_hides_reminder(self):
        now, meal_date = self._meal_window_now()
        self.client.force_login(self.prod_user)
        with patch('django.utils.timezone.localtime', return_value=now):
            resp = self.client.post(reverse('utilities:meal_decline'))
            self.assertEqual(resp.status_code, 302)
            self.assertTrue(
                MealOrderDecline.objects.filter(employee=self.prod_user, meal_date=meal_date).exists(),
            )
            widgets = get_utilities_portal_widgets(self.prod_user)
            meal_widgets = [w for w in widgets if w['title'] == 'Đặt cơm công ty']
            self.assertEqual(len(meal_widgets), 0)

    @override_settings(USE_TZ=True)
    def test_salary_reminder_on_day_18(self):
        open_day = timezone.make_aware(datetime(2026, 5, 18, 10, 0))
        with patch('django.utils.timezone.localtime', return_value=open_day):
            widgets = get_utilities_portal_widgets(self.office_user)
            self.assertEqual(len(widgets), 1)
            self.assertIn('Ứng lương', widgets[0]['title'])

    @override_settings(USE_TZ=True)
    def test_salary_decline_hides_reminder(self):
        open_day = timezone.make_aware(datetime(2026, 5, 18, 14, 0))
        self.client.force_login(self.office_user)
        with patch('django.utils.timezone.localtime', return_value=open_day):
            resp = self.client.post(reverse('utilities:salary_decline'))
            self.assertEqual(resp.status_code, 302)
            month = open_day.date().replace(day=1)
            self.assertTrue(
                SalaryAdvanceDecline.objects.filter(
                    employee=self.office_user,
                    request_month=month,
                ).exists(),
            )
            self.assertEqual(len(get_utilities_portal_widgets(self.office_user)), 0)

    @override_settings(USE_TZ=True)
    def test_portal_dashboard_includes_utilities_widget(self):
        now, _ = self._meal_window_now()
        with patch('django.utils.timezone.localtime', return_value=now):
            widgets = get_portal_dashboard(self.prod_user)
            titles = [w['title'] for w in widgets]
            self.assertIn('Đặt cơm công ty', titles)
            self.assertEqual(get_utilities_pending_count(self.prod_user), 1)

    @override_settings(USE_TZ=True)
    def test_utilities_pending_count_matches_widgets(self):
        now, _ = self._meal_window_now()
        with patch('django.utils.timezone.localtime', return_value=now):
            self.assertEqual(
                get_utilities_pending_count(self.prod_user),
                len(get_utilities_portal_widgets(self.prod_user)),
            )
            self.assertEqual(get_utilities_pending_count(self.office_user), 0)
