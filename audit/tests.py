from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from audit.models import UserActivityLog
from audit.utils import sanitize_mapping, infer_action, build_summary, get_client_device_info, is_private_ip
from audit.summaries import describe_post_highlights, resolve_url_description
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

    def test_is_private_ip(self):
        self.assertTrue(is_private_ip('192.168.1.105'))
        self.assertTrue(is_private_ip('10.0.0.8'))
        self.assertFalse(is_private_ip('103.90.224.203'))

    def test_client_device_from_cookie(self):
        factory = RequestFactory()
        request = factory.get('/')
        request.COOKIES = {
            'jp_hostname': 'JP-HR-PC01',
            'jp_local_ip': '192.168.1.55',
        }
        info = get_client_device_info(request)
        self.assertEqual(info['machine_name'], 'JP-HR-PC01')
        self.assertEqual(info['local_ip'], '192.168.1.55')

    def test_client_device_fallback_private_real_ip(self):
        factory = RequestFactory()
        request = factory.get('/', HTTP_X_REAL_IP='192.168.10.20')
        info = get_client_device_info(request)
        self.assertEqual(info['local_ip'], '192.168.10.20')
        self.assertEqual(info['machine_name'], 'PC-20')

    def test_client_device_ignores_wan_ip(self):
        factory = RequestFactory()
        request = factory.get('/', HTTP_X_REAL_IP='103.90.224.203', REMOTE_ADDR='103.90.224.203')
        info = get_client_device_info(request)
        self.assertIsNone(info['local_ip'])

    def test_infer_action_post_update(self):
        factory = RequestFactory()
        request = factory.post('/dashboard/users/1/edit/')
        self.assertEqual(infer_action(request), UserActivityLog.ACTION_UPDATE)

    def test_resolve_audit_module_path(self):
        self.assertEqual(resolve_module_from_request('/nhat-ky/'), MODULE_AUDIT)


class AuditSummaryTests(TestCase):
    def test_user_add_post_summary(self):
        factory = RequestFactory()
        request = factory.post('/dashboard/users/add/', {
            'full_name': 'Nguyễn Văn A',
            'username': 'nva',
            'employee_code': 'JP001',
            'department': '1',
            'role': 'EMPLOYEE',
        })
        request.user = type('U', (), {'is_authenticated': True, 'username': 'admin', 'get_full_name': lambda s: 'Admin'})()
        request.resolver_match = type('M', (), {
            'url_name': 'user_add',
            'kwargs': {},
        })()

        summary = build_summary(request, UserActivityLog.ACTION_CREATE, 'Nhân sự')
        self.assertIn('tạo nhân viên mới', summary)
        self.assertIn('Nguyễn Văn A', summary)
        self.assertIn('nva', summary)

    def test_user_list_get_summary(self):
        factory = RequestFactory()
        request = factory.get('/dashboard/users/')
        request.user = type('U', (), {'is_authenticated': True, 'username': 'hr', 'get_full_name': lambda s: 'HR User'})()
        request.resolver_match = type('M', (), {'url_name': 'user_list', 'kwargs': {}})()

        summary = build_summary(request, UserActivityLog.ACTION_VIEW, 'Nhân sự')
        self.assertIn('danh sách nhân viên', summary)

    def test_resolve_url_description_with_kwargs(self):
        factory = RequestFactory()
        request = factory.post('/dashboard/users/edit/42/')
        request.resolver_match = type('M', (), {'url_name': 'user_edit', 'kwargs': {'user_id': 42}})()
        desc = resolve_url_description(request, 'user_edit')
        self.assertIn('#42', desc)
        self.assertIn('cập nhật', desc)


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
