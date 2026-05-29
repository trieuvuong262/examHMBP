from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.module_permissions import (
    ALL_MODULE_KEYS,
    MODULE_HRM,
    MODULE_KPI,
    MODULE_PERMISSIONS,
    MODULE_RECRUITMENT,
    MODULE_TRAINING,
    can_manage_permissions,
    get_department_enabled_modules,
    resolve_module_from_request,
    user_can_access_module,
    user_can_edit_module,
)
from hrm.permissions import ROLE_DIRECTOR, ROLE_EMPLOYEE, ROLE_TEAM_LEADER
from hrm.role_permissions import get_role_permissions, role_allows_edit, role_allows_view


class PermissionLogicTests(TestCase):
    def setUp(self):
        self.dept_hr = Department.objects.create(name='Phòng HR Test', sort_order=1)
        self.dept_xuong = Department.objects.create(name='Phòng Xưởng Test', sort_order=2)

        DepartmentMenuPermission.objects.create(
            department=self.dept_hr,
            modules=['announcements', 'hrm', 'kpi', 'training', 'documents', 'permissions'],
        )
        DepartmentMenuPermission.objects.create(
            department=self.dept_xuong,
            modules=['announcements', 'training', 'assessment'],
        )
        # dept không cấu hình module → full quyền (list rỗng)
        self.dept_full = Department.objects.create(name='Phòng Full Test', sort_order=3)
        DepartmentMenuPermission.objects.create(department=self.dept_full, modules=[])

        RoleModulePermission.objects.update_or_create(
            role=ROLE_EMPLOYEE,
            defaults={
                'module_permissions': {
                    'announcements': {'view': True, 'edit': False},
                    'training': {'view': True, 'edit': False},
                    'hrm': {'view': False, 'edit': False},
                    'kpi': {'view': True, 'edit': False},
                    'recruitment': {'view': False, 'edit': False},
                },
            },
        )
        RoleModulePermission.objects.update_or_create(
            role=ROLE_TEAM_LEADER,
            defaults={
                'module_permissions': {
                    'announcements': {'view': True, 'edit': False},
                    'training': {'view': True, 'edit': False},
                    'hrm': {'view': True, 'edit': False},
                    'kpi': {'view': True, 'edit': True},
                    'reports': {'view': True, 'edit': True},
                },
            },
        )

        self.employee = User.objects.create_user(
            username='perm_employee',
            password='testpass123',
        )
        Profile.objects.filter(user=self.employee).update(
            department=self.dept_xuong,
            role=ROLE_EMPLOYEE,
            full_name='NV Test',
        )
        self.employee.refresh_from_db()

        self.team_leader = User.objects.create_user(
            username='perm_leader',
            password='testpass123',
        )
        Profile.objects.filter(user=self.team_leader).update(
            department=self.dept_hr,
            role=ROLE_TEAM_LEADER,
            full_name='Tổ trưởng Test',
        )
        self.team_leader.refresh_from_db()

        self.hr_editor = User.objects.create_user(
            username='perm_hr_editor',
            password='testpass123',
            is_staff=True,
        )
        Profile.objects.filter(user=self.hr_editor).update(
            department=self.dept_hr,
            role=ROLE_DIRECTOR,
            full_name='HR Director Test',
        )
        self.hr_editor.refresh_from_db()

    def test_empty_department_modules_means_full_access(self):
        enabled = get_department_enabled_modules(self.dept_full)
        self.assertEqual(len(enabled), len(ALL_MODULE_KEYS))
        self.assertIn(MODULE_RECRUITMENT, enabled)

    def test_department_restricts_modules(self):
        enabled = get_department_enabled_modules(self.dept_xuong)
        self.assertIn(MODULE_TRAINING, enabled)
        self.assertNotIn(MODULE_HRM, enabled)

    def test_employee_cannot_view_hrm_even_if_dept_allows(self):
        Profile.objects.filter(user=self.team_leader).update(role=ROLE_EMPLOYEE)
        self.team_leader.refresh_from_db()
        self.assertFalse(user_can_access_module(self.team_leader, MODULE_HRM))

    def test_team_leader_can_view_not_edit_hrm_when_role_configured(self):
        self.assertTrue(user_can_access_module(self.team_leader, MODULE_HRM))
        self.assertFalse(user_can_edit_module(self.team_leader, MODULE_HRM))

    def test_team_leader_can_edit_kpi(self):
        self.assertTrue(user_can_edit_module(self.team_leader, MODULE_KPI))

    def test_employee_blocked_from_kpi_when_dept_lacks_module(self):
        self.assertFalse(user_can_access_module(self.employee, MODULE_KPI))

    def test_employee_can_view_training(self):
        self.assertTrue(user_can_access_module(self.employee, MODULE_TRAINING))

    def test_director_in_hr_dept_can_edit_hrm(self):
        self.assertTrue(user_can_edit_module(self.hr_editor, MODULE_HRM))

    def test_resolve_module_urls(self):
        self.assertEqual(resolve_module_from_request('/dashboard/users/'), MODULE_HRM)
        self.assertEqual(resolve_module_from_request('/tai-lieu/'), 'documents')
        self.assertEqual(resolve_module_from_request('/dashboard/permissions/'), MODULE_PERMISSIONS)
        self.assertEqual(
            resolve_module_from_request('/dashboard/departments/1/permissions/'),
            MODULE_PERMISSIONS,
        )
        self.assertEqual(resolve_module_from_request('/dashboard/permissions/roles/EMPLOYEE/'), MODULE_PERMISSIONS)
        self.assertEqual(
            resolve_module_from_request('/dashboard/', 'recruitment'),
            MODULE_RECRUITMENT,
        )

    def test_can_manage_permissions_requires_permissions_edit(self):
        RoleModulePermission.objects.update_or_create(
            role=ROLE_DIRECTOR,
            defaults={
                'module_permissions': {
                    'permissions': {'view': True, 'edit': True},
                    'hrm': {'view': True, 'edit': True},
                },
            },
        )
        self.assertTrue(can_manage_permissions(self.hr_editor))
        self.assertFalse(can_manage_permissions(self.employee))

    def test_hrm_edit_without_permissions_module_cannot_manage(self):
        """Có quyền HRM nhưng không có module Phân quyền — không vào cấu hình."""
        RoleModulePermission.objects.update_or_create(
            role=ROLE_DIRECTOR,
            defaults={
                'module_permissions': {
                    'hrm': {'view': True, 'edit': True},
                    'permissions': {'view': False, 'edit': False},
                },
            },
        )
        Profile.objects.filter(user=self.hr_editor).update(role=ROLE_DIRECTOR)
        self.hr_editor.refresh_from_db()
        self.assertFalse(can_manage_permissions(self.hr_editor))

    def test_role_permission_defaults_seeded(self):
        perms = get_role_permissions(ROLE_DIRECTOR)
        self.assertTrue(perms[MODULE_HRM]['edit'])


class PermissionMiddlewareTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='MW Dept', sort_order=1)
        DepartmentMenuPermission.objects.create(
            department=self.dept,
            modules=['announcements'],
        )
        RoleModulePermission.objects.update_or_create(
            role=ROLE_EMPLOYEE,
            defaults={
                'module_permissions': {
                    'announcements': {'view': True, 'edit': False},
                    'kpi': {'view': True, 'edit': False},
                },
            },
        )
        self.user = User.objects.create_user(username='mw_user', password='testpass123')
        Profile.objects.filter(user=self.user).update(
            department=self.dept,
            role=ROLE_EMPLOYEE,
        )

    def test_middleware_blocks_kpi_url(self):
        client = Client(HTTP_HOST='testserver')
        client.force_login(self.user)
        response = client.get('/kpi/', follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home_portal'))

    def test_middleware_allows_announcements(self):
        client = Client(HTTP_HOST='testserver')
        client.force_login(self.user)
        response = client.get('/announcements/')
        self.assertEqual(response.status_code, 200)

    def test_middleware_blocks_hrm_user_list_for_employee(self):
        """Nhân viên xưởng không có quyền HRM — chặn /dashboard/users/."""
        dept = Department.objects.create(name='MW2', sort_order=9)
        DepartmentMenuPermission.objects.create(
            department=dept,
            modules=['announcements', 'hrm'],
        )
        user = User.objects.create_user(username='mw_hrm_block', password='testpass123')
        Profile.objects.filter(user=user).update(department=dept, role=ROLE_EMPLOYEE)
        client = Client(HTTP_HOST='testserver')
        client.force_login(user)
        response = client.get('/dashboard/users/', follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home_portal'))

    def test_middleware_blocks_permission_config_without_module(self):
        dept = Department.objects.create(name='MW Perm', sort_order=10)
        DepartmentMenuPermission.objects.create(
            department=dept,
            modules=['announcements'],
        )
        user = User.objects.create_user(username='mw_perm', password='testpass123')
        Profile.objects.filter(user=user).update(department=dept, role=ROLE_EMPLOYEE)
        client = Client(HTTP_HOST='testserver')
        client.force_login(user)
        response = client.get('/dashboard/permissions/', follow=False)
        self.assertEqual(response.status_code, 302)

    def test_admin_only_blocks_employee_from_user_list(self):
        client = Client(HTTP_HOST='testserver')
        client.force_login(self.user)
        response = client.get('/dashboard/users/')
        self.assertEqual(response.status_code, 302)


class RolePermissionFormTests(TestCase):
    def test_normalize_edit_implies_view(self):
        from hrm.forms import RolePermissionForm

        form = RolePermissionForm(data={
            'view_hrm': False,
            'edit_hrm': True,
            'view_announcements': True,
            'edit_announcements': False,
        })
        self.assertTrue(form.is_valid(), form.errors)
        perms = form.cleaned_permissions()
        self.assertTrue(perms[MODULE_HRM]['view'])
        self.assertTrue(perms[MODULE_HRM]['edit'])


class ProfileAvatarTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='avatar_user', password='testpass123')
        Profile.objects.filter(user=self.user).update(full_name='Avatar Test')
        self.client = Client()
        self.client.force_login(self.user)

    def test_update_avatar(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        image = SimpleUploadedFile('me.jpg', b'jpeg-bytes', content_type='image/jpeg')
        response = self.client.post(reverse('update_avatar'), {
            'avatar': image,
            'next': '/',
        })
        self.assertEqual(response.status_code, 302)
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.avatar)
        self.assertIn('me', self.user.profile.avatar.name)
