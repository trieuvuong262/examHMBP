from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from feedback.models import Feedback
from hrm.models import Department, DepartmentMenuPermission, PermissionGroup, Profile
from hrm.module_permissions import MODULE_FEEDBACK
from hrm.permissions import ROLE_EMPLOYEE, ROLE_TEAM_LEADER
from hrm.group_permissions import normalize_group_permissions, permissions_from_legacy_role


class FeedbackGranularPermissionTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='Feedback Perm Dept', sort_order=1)
        DepartmentMenuPermission.objects.create(
            department=self.dept,
            modules=['feedback'],
        )

        base = normalize_group_permissions(permissions_from_legacy_role(ROLE_EMPLOYEE))
        view_only = dict(base)
        view_only[MODULE_FEEDBACK] = {
            'view': True,
            'create': False,
            'update': False,
            'delete': False,
            'export': False,
        }
        self.group_view = PermissionGroup.objects.create(
            slug='test-feedback-view',
            name='Feedback view only',
            module_permissions=view_only,
        )

        reviewer = dict(base)
        reviewer[MODULE_FEEDBACK] = {
            'view': True,
            'create': False,
            'update': True,
            'delete': False,
            'export': False,
        }
        self.group_reviewer = PermissionGroup.objects.create(
            slug='test-feedback-reviewer',
            name='Feedback reviewer',
            module_permissions=reviewer,
        )

        self.view_user = User.objects.create_user(username='fb_view', password='testpass123')
        Profile.objects.filter(user=self.view_user).update(
            department=self.dept,
            role=ROLE_EMPLOYEE,
            permission_group=self.group_view,
        )

        self.reviewer = User.objects.create_user(username='fb_reviewer', password='testpass123')
        Profile.objects.filter(user=self.reviewer).update(
            department=self.dept,
            role=ROLE_TEAM_LEADER,
            permission_group=self.group_reviewer,
        )

        self.feedback = Feedback.objects.create(
            submitter=self.view_user,
            title='Test feedback',
            body='Content',
        )

        self.client = Client(HTTP_HOST='testserver')

    def test_view_only_can_open_create_form(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('feedback:create'))
        self.assertEqual(response.status_code, 200)

    def test_view_only_can_submit_feedback(self):
        self.client.force_login(self.view_user)
        response = self.client.post(reverse('feedback:create'), {
            'title': 'Góp ý mới',
            'body': 'Nội dung góp ý',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Feedback.objects.filter(title='Góp ý mới').count(), 1)

    def test_view_only_cannot_open_feedback_list(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('feedback:list'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home_portal'))

    def test_reviewer_can_open_feedback_list(self):
        self.client.force_login(self.reviewer)
        response = self.client.get(reverse('feedback:list'))
        self.assertEqual(response.status_code, 200)

    def test_view_only_cannot_open_feedback_detail(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('feedback:detail', args=[self.feedback.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home_portal'))

    def test_reviewer_can_open_feedback_detail(self):
        self.client.force_login(self.reviewer)
        response = self.client.get(reverse('feedback:detail', args=[self.feedback.pk]))
        self.assertEqual(response.status_code, 200)
