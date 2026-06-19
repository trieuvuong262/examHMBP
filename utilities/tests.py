from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.module_permissions import MODULE_UTILITIES
from hrm.permissions import ROLE_EMPLOYEE
from utilities.meal_rules import is_meal_order_window_open, meal_order_window_for
from utilities.models import MealDish, MealOrder, SalaryAdvanceRequest
from utilities.salary_rules import MAX_SALARY_ADVANCE, is_salary_advance_open


class UtilitiesAccessTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(name='Utilities Dept', sort_order=1)
        DepartmentMenuPermission.objects.create(department=dept, modules=['utilities'])
        RoleModulePermission.objects.update_or_create(
            role=ROLE_EMPLOYEE,
            defaults={
                'module_permissions': {
                    'utilities': {'view': True, 'edit': True},
                },
            },
        )
        self.user = User.objects.create_user(username='util_nv', password='test')
        Profile.objects.filter(user=self.user).update(
            department=dept,
            role=ROLE_EMPLOYEE,
            full_name='Util NV',
            is_employed=True,
        )
        self.client = Client(HTTP_HOST='testserver')
        self.client.force_login(self.user)

    def test_meal_home_loads(self):
        resp = self.client.get(reverse('utilities:meal_home'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Đặt cơm công ty')

    def test_salary_home_loads(self):
        resp = self.client.get(reverse('utilities:salary_home'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Ứng lương')

    def test_seed_dishes_exist(self):
        self.assertGreaterEqual(MealDish.objects.count(), 20)


class UtilitiesRulesTests(TestCase):
    def test_salary_advance_max(self):
        self.assertEqual(MAX_SALARY_ADVANCE, Decimal('3000000'))

    def test_salary_advance_form_accepts_max_amount(self):
        from unittest.mock import patch

        from utilities.forms import SalaryAdvanceForm

        with patch('utilities.forms.is_salary_advance_open', return_value=True):
            form = SalaryAdvanceForm({'amount': '3000000', 'note': ''})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['amount'], Decimal('3000000'))

    def test_meal_window_boundaries(self):
        from datetime import date, datetime, time, timedelta

        meal_date = date(2026, 6, 10)
        start, end = meal_order_window_for(meal_date)
        inside = timezone.make_aware(datetime.combine(meal_date - timedelta(days=1), time(17, 0)))
        self.assertTrue(is_meal_order_window_open(meal_date, now=inside))
        outside = timezone.make_aware(datetime.combine(meal_date - timedelta(days=1), time(21, 0)))
        self.assertFalse(is_meal_order_window_open(meal_date, now=outside))

    def test_salary_open_days(self):
        from datetime import datetime

        open_day = timezone.make_aware(datetime(2026, 5, 18, 10, 0))
        closed_day = timezone.make_aware(datetime(2026, 5, 17, 10, 0))
        self.assertTrue(is_salary_advance_open(now=open_day))
        self.assertFalse(is_salary_advance_open(now=closed_day))
