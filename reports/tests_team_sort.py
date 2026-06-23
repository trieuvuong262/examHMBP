from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.permissions import ROLE_EMPLOYEE, ROLE_TEAM_LEADER
from reports.models import DailyWorkReport
from reports.report_profile import REPORT_PROFILE_OFFICE
from reports.team_sort import sort_team_department_groups, TEAM_SORT_STATUS
from reports.week_utils import monday_of


class TeamSortTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(name='Sort Dept', sort_order=1, report_profile=REPORT_PROFILE_OFFICE)
        DepartmentMenuPermission.objects.create(department=dept, modules=['reports'])
        RoleModulePermission.objects.update_or_create(
            role=ROLE_TEAM_LEADER,
            defaults={'module_permissions': {'reports': {'view': True, 'edit': True}}},
        )
        self.leader = User.objects.create_user(username='sort_leader', password='x')
        Profile.objects.filter(user=self.leader).update(
            department=dept,
            role=ROLE_TEAM_LEADER,
            full_name='Leader Sort',
            is_employed=True,
        )
        self.alpha = User.objects.create_user(username='alpha_mem', password='x')
        Profile.objects.filter(user=self.alpha).update(
            department=dept,
            role=ROLE_EMPLOYEE,
            full_name='Alpha Member',
            is_employed=True,
        )
        self.zulu = User.objects.create_user(username='zulu_mem', password='x')
        Profile.objects.filter(user=self.zulu).update(
            department=dept,
            role=ROLE_EMPLOYEE,
            full_name='Zulu Member',
            is_employed=True,
        )
        self.leader.profile.subordinates.add(self.alpha, self.zulu)

    def test_team_vp_sort_header_links(self):
        self.client.force_login(self.leader)
        resp = self.client.get(reverse('reports:team_vp'))
        self.assertContains(resp, 'jp-table-sort-link')
        self.assertContains(resp, 'sort=member')
        self.assertContains(resp, 'sort=status')

    def test_team_vp_sort_by_member_desc(self):
        week = monday_of(date.today())
        DailyWorkReport.objects.create(
            employee=self.alpha,
            report_date=week,
            report_profile=REPORT_PROFILE_OFFICE,
            report_period='week',
            status=DailyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )
        DailyWorkReport.objects.create(
            employee=self.zulu,
            report_date=week,
            report_profile=REPORT_PROFILE_OFFICE,
            report_period='week',
            status=DailyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )
        self.client.force_login(self.leader)
        resp = self.client.get(reverse('reports:team_vp'), {
            'from': week.isoformat(),
            'to': (week + timedelta(days=6)).isoformat(),
            'sort': 'member',
            'dir': 'desc',
        })
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertLess(content.index('Zulu Member'), content.index('Alpha Member'))

    def test_sort_team_department_groups_by_status(self):
        rows = [
            {'member': self.zulu, 'report': None},
            {
                'member': self.alpha,
                'report': DailyWorkReport(
                    status=DailyWorkReport.STATUS_SUBMITTED,
                    report_period='day',
                ),
            },
        ]
        groups = [{'label': 'G', 'rows': rows}]
        sorted_groups = sort_team_department_groups(groups, TEAM_SORT_STATUS, 'asc')
        statuses = [r.get('report') and r['report'].status for r in sorted_groups[0]['rows']]
        self.assertEqual(statuses[0], None)
        self.assertEqual(statuses[1], DailyWorkReport.STATUS_SUBMITTED)
