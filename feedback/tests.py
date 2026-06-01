from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from assessment.portal_widgets import get_portal_dashboard
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
        self.manager = self._user('hr1', ROLE_TEAM_LEADER)
        self.client = Client()

    def _user(self, username, role):
        user = User.objects.create_user(username=username, password='pass')
        Profile.objects.filter(user=user).update(
            department=self.dept,
            role=role,
        )
        return User.objects.select_related('profile').get(pk=user.pk)

    def test_employee_can_submit_feedback(self):
        self.client.login(username='nv1', password='pass')
        resp = self.client.post(reverse('feedback:create'), {
            'title': 'Cải thiện quy trình',
            'body': 'Đề xuất rút gọn bước duyệt',
            'is_anonymous': 'on',
        })
        self.assertEqual(resp.status_code, 302)
        feedback = Feedback.objects.get()
        self.assertTrue(feedback.is_anonymous)
        self.assertEqual(feedback.submitter_display(), 'Ẩn danh')

    def test_employee_cannot_view_list_or_detail(self):
        feedback = Feedback.objects.create(
            submitter=self.employee,
            title='Riêng tư',
            body='Nội dung',
        )
        self.client.login(username='nv1', password='pass')
        self.assertEqual(self.client.get(reverse('feedback:list')).status_code, 302)
        self.assertEqual(self.client.get(reverse('feedback:detail', args=[feedback.pk])).status_code, 302)

    def test_manager_sees_submitter_when_not_anonymous(self):
        Feedback.objects.create(
            submitter=self.employee,
            title='Góp ý IT',
            body='Máy chậm',
            is_anonymous=False,
        )
        self.client.login(username='hr1', password='pass')
        resp = self.client.get(reverse('feedback:list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'nv1')

    def test_manager_sees_anonymous_label(self):
        Feedback.objects.create(
            submitter=self.employee,
            title='Góp ý ẩn danh',
            body='Nội dung',
            is_anonymous=True,
        )
        self.client.login(username='hr1', password='pass')
        resp = self.client.get(reverse('feedback:detail', args=[Feedback.objects.get().pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Ẩn danh')
        self.assertNotContains(resp, 'nv1')

    def test_home_widget_for_manager(self):
        Feedback.objects.create(
            submitter=self.employee,
            title='Widget test',
            body='Body',
        )
        widgets = get_portal_dashboard(self.manager)
        feedback_widgets = [w for w in widgets if w.get('title') == 'Góp ý chưa xem']
        self.assertEqual(len(feedback_widgets), 1)
        self.assertEqual(feedback_widgets[0]['badge'], 1)

    def test_home_widget_hidden_when_all_viewed(self):
        feedback = Feedback.objects.create(
            submitter=self.employee,
            title='Đã xem',
            body='Body',
        )
        feedback.mark_viewed_by(self.manager)
        widgets = get_portal_dashboard(self.manager)
        self.assertFalse(any(w.get('title') == 'Góp ý chưa xem' for w in widgets))

    def test_viewing_marks_feedback_as_read(self):
        feedback = Feedback.objects.create(
            submitter=self.employee,
            title='Cần xem',
            body='Nội dung',
        )
        self.client.login(username='hr1', password='pass')
        self.client.get(reverse('feedback:detail', args=[feedback.pk]))
        feedback.refresh_from_db()
        self.assertIsNotNone(feedback.viewed_at)
        self.assertEqual(feedback.viewed_by_id, self.manager.id)

    def test_no_home_widget_for_employee(self):
        Feedback.objects.create(
            submitter=self.employee,
            title='Widget test',
            body='Body',
        )
        widgets = get_portal_dashboard(self.employee)
        self.assertFalse(any(w.get('title') == 'Góp ý chưa xem' for w in widgets))
