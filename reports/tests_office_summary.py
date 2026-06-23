from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.permissions import ROLE_EMPLOYEE, ROLE_TEAM_LEADER
from reports.models import DailyWorkReport
from reports.office_content import office_report_summary_text
from reports.report_profile import REPORT_PROFILE_OFFICE


class OfficeReportSummaryTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(name='Summary Dept', sort_order=1)
        DepartmentMenuPermission.objects.create(department=dept, modules=['reports'])
        RoleModulePermission.objects.update_or_create(
            role=ROLE_TEAM_LEADER,
            defaults={'module_permissions': {'reports': {'view': True, 'edit': True}}},
        )
        self.leader = User.objects.create_user(username='sum_leader', password='x')
        Profile.objects.filter(user=self.leader).update(
            department=dept,
            role=ROLE_TEAM_LEADER,
            full_name='Leader',
            is_employed=True,
        )
        self.member = User.objects.create_user(username='sum_mem', password='x')
        Profile.objects.filter(user=self.member).update(
            department=dept,
            role=ROLE_EMPLOYEE,
            full_name='Member',
            is_employed=True,
        )
        self.leader.profile.subordinates.add(self.member)

    def test_summary_only_shows_filled_sections(self):
        report = DailyWorkReport.objects.create(
            employee=self.member,
            report_date=timezone.localdate(),
            report_profile=REPORT_PROFILE_OFFICE,
            status=DailyWorkReport.STATUS_SUBMITTED,
            links='https://example.com',
            submitted_at=timezone.now(),
        )
        self.assertEqual(office_report_summary_text(report), 'Link')

    def test_summary_includes_vanban_and_bang_when_present(self):
        report = DailyWorkReport.objects.create(
            employee=self.member,
            report_date=timezone.localdate(),
            report_profile=REPORT_PROFILE_OFFICE,
            document_html='<p>Nội dung văn bản</p>',
            spreadsheet_json={'columns': ['A'], 'rows': [['1']]},
            status=DailyWorkReport.STATUS_DRAFT,
        )
        self.assertEqual(office_report_summary_text(report), 'Văn bản · Bảng')

    def test_team_page_summary_only_link(self):
        from django.test import Client
        from django.urls import reverse

        report = DailyWorkReport.objects.create(
            employee=self.member,
            report_date=timezone.localdate(),
            report_profile=REPORT_PROFILE_OFFICE,
            status=DailyWorkReport.STATUS_SUBMITTED,
            links='https://only-link.example',
            submitted_at=timezone.now(),
        )
        client = Client(HTTP_HOST='testserver')
        client.force_login(self.leader)
        resp = client.get(reverse('reports:team_vp'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Link')
        self.assertNotContains(resp, 'Văn bản + Bảng')
        self.assertNotContains(resp, 'Văn bản · Bảng')
