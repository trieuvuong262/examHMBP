
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from hrm.models import Department, Profile
from hrm.permissions import (
    ROLE_DEPARTMENT_HEAD,
    ROLE_DIRECTOR,
    ROLE_DIVISION_HEAD,
    ROLE_EMPLOYEE,
    ROLE_TEAM_LEADER,
)
from reports.production_team import (
    _append_production_member_rows,
    is_production_no_report_exempt,
    production_team_status_counts,
)


class ProductionNoReportExemptTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='SX Exempt Dept', sort_order=1)

    def _user(self, username, role):
        user = User.objects.create_user(username=username, password='test')
        Profile.objects.filter(user=user).update(
            department=self.dept, role=role, full_name=username, is_employed=True,
        )
        user.refresh_from_db()
        return user

    def test_exempt_roles(self):
        self.assertTrue(is_production_no_report_exempt(self._user('dh', ROLE_DIVISION_HEAD)))
        self.assertTrue(is_production_no_report_exempt(self._user('ph', ROLE_DEPARTMENT_HEAD)))
        self.assertTrue(is_production_no_report_exempt(self._user('dir', ROLE_DIRECTOR)))
        self.assertFalse(is_production_no_report_exempt(self._user('tl', ROLE_TEAM_LEADER)))
        self.assertFalse(is_production_no_report_exempt(self._user('nv', ROLE_EMPLOYEE)))

    def test_append_skips_empty_rows_for_division_head(self):
        manager = self._user('mgr_skip', ROLE_DIVISION_HEAD)
        worker = self._user('wk_show', ROLE_EMPLOYEE)
        day = date.today()
        rows = []
        _append_production_member_rows(rows, manager, [], lambda r: True, date_from=day, date_to=day)
        self.assertEqual(rows, [])
        _append_production_member_rows(rows, worker, [], lambda r: True, date_from=day, date_to=day)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['production_report_count'], 0)

    def test_status_counts_exclude_exempt(self):
        manager = self._user('mgr_cnt', ROLE_DEPARTMENT_HEAD)
        worker = self._user('wk_cnt', ROLE_EMPLOYEE)
        counts = production_team_status_counts(
            [manager.id, worker.id],
            {},
            lambda r: True,
            exempt_no_report_ids={manager.id},
        )
        self.assertEqual(counts['no_report'], 1)
        self.assertEqual(counts['submitted'], 0)
