from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from feedback.models import Feedback
from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.module_permissions import MODULE_FEEDBACK
from hrm.permissions import ROLE_EMPLOYEE, ROLE_TEAM_LEADER


class FeedbackAccessTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='Phòng Test', sort_order=0)
        DepartmentMenuPermission.objects.create(
            department=self.dept,
            modules=[MODULE_FEEDBACK],
        )
        RoleModulePermission.objects.update_or_create(
            role=ROLE_EMPLOYEE,
            defaults={'module_permissions': {MODULE_FEEDBACK: {'view': True, 'edit': False}}},
        )
        RoleModulePermission.objects.update_or_create(
            role=ROLE_TEAM_LEADER,
            defaults={'module_permissions': {MODULE_FEEDBACK: {'view': True, 'edit': True}}},
        )

        self.employee = self._user('nv1', ROLE_EMPLOYEE)
        self.hr = self._user('hr1', ROLE_TEAM_LEADER)
        self.client = Client()

    def _user(self, username, role):
        user = User.objects.create_user(username=username, password='pass')
        Profile.objects.filter(user=user).update(
            department=self.dept,
            role=role,
        )
        return user

    def test_employee_can_create_and_view_own_feedback(self):
        self.client.login(username='nv1', password='pass')
        resp = self.client.get(reverse('feedback:create'))
        self.assertEqual(resp.status_code, 200)

        resp = self.client.post(reverse('feedback:create'), {
            'title': 'Cải thiện quy trình',
            'category': Feedback.CATEGORY_PROCESS,
            'body': 'Đề xuất rút gọn bước duyệt',
        })
        self.assertEqual(resp.status_code, 302)
        feedback = Feedback.objects.get()
        self.assertEqual(feedback.submitter_id, self.employee.id)

        resp = self.client.get(reverse('feedback:detail', args=[feedback.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_employee_cannot_view_others_feedback(self):
        other = self._user('nv2', ROLE_EMPLOYEE)
        feedback = Feedback.objects.create(
            submitter=other,
            title='Riêng tư',
            body='Nội dung',
        )
        self.client.login(username='nv1', password='pass')
        resp = self.client.get(reverse('feedback:detail', args=[feedback.pk]))
        self.assertEqual(resp.status_code, 302)

    def test_hr_can_respond(self):
        feedback = Feedback.objects.create(
            submitter=self.employee,
            title='Góp ý IT',
            body='Máy chậm',
            category=Feedback.CATEGORY_TOOL,
        )
        self.client.login(username='hr1', password='pass')
        resp = self.client.post(reverse('feedback:detail', args=[feedback.pk]), {
            'action': 'respond',
            'status': Feedback.STATUS_RESOLVED,
            'body': 'Đã kiểm tra và xử lý',
        })
        self.assertEqual(resp.status_code, 302)
        feedback.refresh_from_db()
        self.assertEqual(feedback.status, Feedback.STATUS_RESOLVED)
        self.assertEqual(feedback.replies.count(), 1)

    def test_review_list_requires_edit_permission(self):
        self.client.login(username='nv1', password='pass')
        resp = self.client.get(reverse('feedback:review_list'))
        self.assertEqual(resp.status_code, 302)

        self.client.login(username='hr1', password='pass')
        resp = self.client.get(reverse('feedback:review_list'))
        self.assertEqual(resp.status_code, 200)
