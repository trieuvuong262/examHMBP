from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from audit.models import UserActivityLog
from audit.utils import sanitize_mapping, infer_action
from django.test import RequestFactory

from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.module_permissions import MODULE_AUDIT, resolve_module_from_request, user_can_access_module
from hrm.permissions import ROLE_DIRECTOR, ROLE_EMPLOYEE


class AuditUtilsTests(TestCase):
    def test_sanitize_password_fields(self):
        data = {'username': 'admin', 'password': 'secret123', 'csrfmiddlewaretoken': 'abc'}
        cleaned = sanitize_mapping(data)
        self.assertEqual(cleaned['username'], 'admin')
        self.assertEqual(cleaned['password'], '***')
        self.assertEqual(cleaned['csrfmiddlewaretoken'], '***')

    def test_infer_action_post_update(self):
        factory = RequestFactory()
        request = factory.post('/dashboard/users/1/edit/')
        self.assertEqual(infer_action(request), UserActivityLog.ACTION_UPDATE)

    def test_resolve_audit_module_path(self):
        self.assertEqual(resolve_module_from_request('/nhat-ky/'), MODULE_AUDIT)


class AuditAccessTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='HR Audit', sort_order=1)
        DepartmentMenuPermission.objects.create(
            department=self.dept,
            modules=['audit', 'announcements'],
        )
        RoleModulePermission.objects.update_or_create(
            role=ROLE_DIRECTOR,
            defaults={'module_permissions': {MODULE_AUDIT: {'view': True, 'edit': True}}},
        )
        RoleModulePermission.objects.update_or_create(
            role=ROLE_EMPLOYEE,
            defaults={'module_permissions': {MODULE_AUDIT: {'view': False, 'edit': False}}},
        )

        self.director = User.objects.create_user(username='audit_director', password='testpass123')
        director_profile = Profile.objects.get(user=self.director)
        director_profile.department = self.dept
        director_profile.role = ROLE_DIRECTOR
        director_profile.full_name = 'GD Audit'
        director_profile.save()

        self.employee = User.objects.create_user(username='audit_employee', password='testpass123')
        employee_profile = Profile.objects.get(user=self.employee)
        employee_profile.department = self.dept
        employee_profile.role = ROLE_EMPLOYEE
        employee_profile.full_name = 'NV Audit'
        employee_profile.save()

        self.client = Client()

    def test_director_can_access_audit_module(self):
        self.director.refresh_from_db()
        self.assertTrue(user_can_access_module(self.director, MODULE_AUDIT))

    def test_employee_cannot_access_audit_module(self):
        self.assertFalse(user_can_access_module(self.employee, MODULE_AUDIT))

    def test_audit_list_requires_permission(self):
        self.client.force_login(self.employee)
        response = self.client.get(reverse('audit:log_list'))
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.director)
        response = self.client.get(reverse('audit:log_list'))
        self.assertEqual(response.status_code, 200)

    def test_create_activity_log_via_post(self):
        self.client.force_login(self.director)
        self.client.get(reverse('home_portal'))
        self.assertTrue(
            UserActivityLog.objects.filter(
                username='audit_director',
                action=UserActivityLog.ACTION_VIEW,
            ).exists()
        )
