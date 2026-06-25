from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.permissions import ROLE_EMPLOYEE, ROLE_TEAM_LEADER


@override_settings(ALLOWED_HOSTS=['testserver', 'portal.justplay.vn'])
class ForcePasswordChangePolicyTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(name='HR Test', sort_order=1)
        DepartmentMenuPermission.objects.create(department=dept, modules=['hrm', 'reports'])
        RoleModulePermission.objects.update_or_create(
            role=ROLE_EMPLOYEE,
            defaults={'module_permissions': {'reports': {'view': True, 'edit': True, 'create': True}}},
        )
        RoleModulePermission.objects.update_or_create(
            role=ROLE_TEAM_LEADER,
            defaults={
                'module_permissions': {
                    'hrm': {'view': True, 'edit': True, 'create': True, 'update': True},
                    'reports': {'view': True, 'edit': True, 'create': True},
                },
            },
        )
        self.employee = User.objects.create_user(username='nv.test', password='justplay@123')
        Profile.objects.filter(user=self.employee).update(
            department=dept,
            role=ROLE_EMPLOYEE,
            full_name='NV Test',
            is_employed=True,
            must_change_password=False,
        )
        self.hr = User.objects.create_user(username='hr.test', password='hrpass', is_staff=True)
        Profile.objects.filter(user=self.hr).update(
            department=dept,
            role=ROLE_TEAM_LEADER,
            full_name='HR Test',
            is_employed=True,
        )
        self.client = Client(HTTP_HOST='testserver')

    def test_login_redirects_to_change_password_when_flag_set(self):
        Profile.require_password_change(self.employee)
        self.client.login(username='nv.test', password='justplay@123')
        resp = self.client.get(reverse('home_portal'), follow=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('password_change'), resp['Location'])

    def test_after_password_change_can_access_portal(self):
        Profile.require_password_change(self.employee)
        self.client.login(username='nv.test', password='justplay@123')
        resp = self.client.post(
            reverse('password_change'),
            {
                'old_password': 'justplay@123',
                'new_password1': 'MyNewPass123!',
                'new_password2': 'MyNewPass123!',
            },
            follow=True,
        )
        self.employee.refresh_from_db()
        self.assertFalse(self.employee.profile.must_change_password)
        self.assertEqual(resp.status_code, 200)
        home = self.client.get(reverse('home_portal'))
        self.assertEqual(home.status_code, 200)

    def test_hr_password_reset_sets_must_change_flag(self):
        self.client.force_login(self.hr)
        resp = self.client.post(reverse('user_password_reset', args=[self.employee.pk]))
        self.assertEqual(resp.status_code, 200)
        self.employee.profile.refresh_from_db()
        self.assertTrue(self.employee.profile.must_change_password)

    def test_require_password_change_active_command(self):
        from django.core.management import call_command

        self.assertFalse(self.employee.profile.must_change_password)
        call_command('require_password_change_active')
        self.employee.profile.refresh_from_db()
        self.assertTrue(self.employee.profile.must_change_password)
