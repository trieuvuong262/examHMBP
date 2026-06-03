from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from hrm.models import (
    Department,
    DepartmentMenuPermission,
    Division,
    PermissionGroup,
    Profile,
    RoleModulePermission,
)
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
    user_can_export_module,
)
from hrm.group_permissions import normalize_group_permissions, permissions_from_legacy_role
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
            permission_group=None,
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
            permission_group=None,
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
            permission_group=None,
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


class PermissionGroupTests(TestCase):
    def setUp(self):
        self.dept_hr = Department.objects.create(name='PG HR', sort_order=1)
        DepartmentMenuPermission.objects.create(
            department=self.dept_hr,
            modules=['hrm', 'announcements', 'training'],
        )

        employee_legacy = permissions_from_legacy_role(ROLE_EMPLOYEE)
        self.group_sx = PermissionGroup.objects.create(
            slug='test-nv-sx',
            name='Test NV Sản xuất',
            module_permissions=employee_legacy,
        )
        hcns_perms = normalize_group_permissions(employee_legacy)
        hcns_perms['hrm'] = {
            'view': True,
            'create': True,
            'update': True,
            'delete': True,
            'export': True,
        }
        self.group_hcns = PermissionGroup.objects.create(
            slug='test-nv-hcns',
            name='Test NV HCNS',
            module_permissions=hcns_perms,
        )

        self.sx_user = User.objects.create_user(username='pg_sx', password='testpass123')
        Profile.objects.filter(user=self.sx_user).update(
            department=self.dept_hr,
            role=ROLE_EMPLOYEE,
            permission_group=self.group_sx,
        )
        self.hcns_user = User.objects.create_user(username='pg_hcns', password='testpass123')
        Profile.objects.filter(user=self.hcns_user).update(
            department=self.dept_hr,
            role=ROLE_EMPLOYEE,
            permission_group=self.group_hcns,
        )
        self.hcns_user.refresh_from_db()

    def test_production_staff_cannot_edit_hrm(self):
        self.assertTrue(user_can_access_module(self.sx_user, MODULE_HRM) is False or not user_can_edit_module(self.sx_user, MODULE_HRM))
        self.assertFalse(user_can_edit_module(self.sx_user, MODULE_HRM))

    def test_hcns_staff_can_edit_and_export_hrm(self):
        self.assertTrue(user_can_edit_module(self.hcns_user, MODULE_HRM))
        self.assertTrue(user_can_export_module(self.hcns_user, MODULE_HRM))

    def test_permission_group_urls_resolve(self):
        self.assertEqual(
            resolve_module_from_request('/dashboard/permissions/groups/1/edit/'),
            MODULE_PERMISSIONS,
        )


class DepartmentPermissionTemplateTests(TestCase):
    def test_each_department_has_two_groups(self):
        from hrm.department_permission_templates import DEPARTMENT_PERMISSION_TEMPLATES
        self.assertEqual(len(DEPARTMENT_PERMISSION_TEMPLATES), 9)
        for item in DEPARTMENT_PERMISSION_TEMPLATES:
            self.assertIn('employee', item)
            self.assertIn('manager', item)

    def test_hcns_employee_can_edit_hrm_in_matrix(self):
        from hrm.department_permission_templates import DEPARTMENT_PERMISSION_TEMPLATES
        hcns = next(t for t in DEPARTMENT_PERMISSION_TEMPLATES if t['code'] == 'hcns')
        hrm = hcns['employee']['hrm']
        self.assertTrue(hrm['view'])
        self.assertTrue(hrm['update'])


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
            permission_group=None,
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

    def test_agent_gate_allowed_without_equipment_module(self):
        """Trang bắt cài agent không thuộc quyền menu Thiết bị — tránh redirect loop."""
        from django.test import override_settings

        client = Client(HTTP_HOST='testserver')
        client.force_login(self.user)
        with override_settings(EQUIPMENT_REQUIRE_AGENT_INSTALL=True, EQUIPMENT_AGENT_SECRET='sec'):
            response = client.get(
                '/thiet-bi/agent/yeu-cau-cai/',
                HTTP_USER_AGENT='Mozilla/5.0 Windows NT 10.0',
                follow=False,
            )
        self.assertEqual(response.status_code, 200)

    def test_home_to_agent_gate_no_redirect_loop_without_equipment_module(self):
        from django.test import override_settings

        client = Client(HTTP_HOST='testserver')
        client.force_login(self.user)
        with override_settings(EQUIPMENT_REQUIRE_AGENT_INSTALL=True, EQUIPMENT_AGENT_SECRET='sec'):
            response = client.get(
                '/',
                HTTP_USER_AGENT='Mozilla/5.0 Windows NT 10.0',
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        final = response.redirect_chain[-1][0] if response.redirect_chain else response.request['PATH_INFO']
        self.assertIn('/thiet-bi/agent/yeu-cau-cai', final)
        self.assertLessEqual(len(response.redirect_chain), 2)

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

    @staticmethod
    def _sample_jpeg_bytes(width=320, height=240):
        from io import BytesIO

        from PIL import Image

        buf = BytesIO()
        Image.new('RGB', (width, height), color=(220, 38, 38)).save(buf, format='JPEG')
        return buf.getvalue()

    def test_prepare_avatar_image_resizes_to_150(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from hrm.avatar_utils import AVATAR_SIZE, prepare_avatar_image

        upload = SimpleUploadedFile('wide.jpg', self._sample_jpeg_bytes(), content_type='image/jpeg')
        prepared = prepare_avatar_image(upload)
        from PIL import Image

        img = Image.open(prepared)
        self.assertEqual(img.size, (AVATAR_SIZE, AVATAR_SIZE))

    def test_update_avatar(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        image = SimpleUploadedFile('me.jpg', self._sample_jpeg_bytes(), content_type='image/jpeg')
        response = self.client.post(reverse('update_avatar'), {
            'avatar': image,
            'next': '/',
        })
        self.assertEqual(response.status_code, 302)
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.avatar)
        self.assertIn('me', self.user.profile.avatar.name)

    def test_user_list_avatar_zoomable(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        image = SimpleUploadedFile('face.jpg', self._sample_jpeg_bytes(), content_type='image/jpeg')
        self.client.post(reverse('update_avatar'), {'avatar': image, 'next': '/'})
        RoleModulePermission.objects.update_or_create(
            role=ROLE_DIRECTOR,
            defaults={'module_permissions': {MODULE_HRM: {'view': True, 'edit': True}}},
        )
        Profile.objects.filter(user=self.user).update(role=ROLE_DIRECTOR, is_employed=True, permission_group=None)
        response = self.client.get(reverse('user_list'))
        self.assertContains(response, 'data-jp-avatar-zoom')
        self.assertContains(response, 'jpAvatarZoomModal')


class UserAddFormTests(TestCase):
    def setUp(self):
        RoleModulePermission.objects.update_or_create(
            role=ROLE_DIRECTOR,
            defaults={'module_permissions': {MODULE_HRM: {'view': True, 'edit': True}}},
        )
        self.admin = User.objects.create_user(username='hr_add', password='testpass123', is_staff=True)
        Profile.objects.filter(user=self.admin).update(
            role=ROLE_DIRECTOR,
            full_name='HR Add',
            is_employed=True,
            permission_group=None,
        )
        self.client = Client(HTTP_HOST='testserver')
        self.client.force_login(self.admin)

    def test_user_add_get_prefills_password(self):
        response = self.client.get(reverse('user_add'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="password"')

    def test_user_add_post_success_without_email(self):
        response = self.client.post(reverse('user_add'), {
            'username': 'newstaff01',
            'password': 'TestPass1',
            'email': '',
            'full_name': 'Nguyễn Văn Mới',
            'role': ROLE_EMPLOYEE,
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='newstaff01').exists())

    def test_user_add_post_shows_errors_when_missing_name(self):
        response = self.client.post(reverse('user_add'), {
            'username': 'x',
            'password': 'TestPass1',
            'full_name': '',
            'role': ROLE_EMPLOYEE,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Không lưu được')
        self.assertContains(response, 'Họ và tên')


class UserSearchTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(name='Phòng May', sort_order=1)
        RoleModulePermission.objects.update_or_create(
            role=ROLE_DIRECTOR,
            defaults={'module_permissions': {MODULE_HRM: {'view': True, 'edit': True}}},
        )
        self.admin = User.objects.create_user(username='hr_admin', password='testpass123', is_staff=True)
        Profile.objects.filter(user=self.admin).update(
            role=ROLE_DIRECTOR,
            full_name='HR Admin',
            is_employed=True,
            permission_group=None,
        )
        self.target = User.objects.create_user(username='annt', password='testpass123', first_name='An')
        Profile.objects.filter(user=self.target).update(
            full_name='Nguyễn Văn An',
            employee_code='NV12345',
            department=dept,
            is_employed=True,
        )
        self.other = User.objects.create_user(username='other_user', password='testpass123')
        Profile.objects.filter(user=self.other).update(full_name='Trần Văn B', is_employed=True)
        self.client = Client(HTTP_HOST='testserver')
        self.client.force_login(self.admin)

    def test_search_by_employee_code_finds_user(self):
        response = self.client.get(reverse('user_list'), {'q': 'NV12345'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nguyễn Văn An')
        self.assertNotContains(response, 'Trần Văn B')

    def test_search_by_username_finds_user(self):
        response = self.client.get(reverse('user_list'), {'q': 'annt'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nguyễn Văn An')

    def test_user_list_hides_system_admin_account(self):
        User.objects.create_user(username='admin', password='testpass123', is_superuser=True)
        response = self.client.get(reverse('user_list'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '>admin<')
        self.assertNotContains(response, '@admin')

    def test_user_list_filter_by_department(self):
        dept_may = Department.objects.get(name='Phòng May')
        response = self.client.get(reverse('user_list'), {'department': str(dept_may.pk)})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nguyễn Văn An')
        self.assertNotContains(response, 'Trần Văn B')

    def test_user_list_filter_unassigned_department(self):
        response = self.client.get(reverse('user_list'), {'department': 'none'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Trần Văn B')
        self.assertNotContains(response, 'Nguyễn Văn An')

    def test_hr_edit_can_update_other_user_avatar(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        image = SimpleUploadedFile(
            'staff.jpg',
            ProfileAvatarTests._sample_jpeg_bytes(),
            content_type='image/jpeg',
        )
        response = self.client.post(reverse('user_edit', args=[self.target.id]), {
            'username': 'annt',
            'email': 'annt@justplay.vn',
            'full_name': 'Nguyễn Văn An',
            'employee_code': 'NV12345',
            'role': ROLE_EMPLOYEE,
            'avatar': image,
        })
        self.assertEqual(response.status_code, 302)
        self.target.profile.refresh_from_db()
        self.assertTrue(self.target.profile.avatar)
        self.assertIn('staff', self.target.profile.avatar.name)


class MediaCleanupTests(TestCase):
    def test_normalize_media_relative_path(self):
        from hrm.media_cleanup import normalize_media_relative_path

        self.assertEqual(normalize_media_relative_path('avatars/2026/05/me.jpg'), 'avatars/2026/05/me.jpg')
        self.assertEqual(normalize_media_relative_path('/media/avatars/x.jpg'), 'avatars/x.jpg')
        self.assertEqual(
            normalize_media_relative_path('https://portal.justplay.vn/media/documents/pdf/a.pdf'),
            'documents/pdf/a.pdf',
        )

    def test_cleanup_orphan_media_dry_run(self):
        import tempfile
        from pathlib import Path

        from django.conf import settings
        from django.test import override_settings

        from hrm.media_cleanup import cleanup_orphan_media

        with tempfile.TemporaryDirectory() as tmp:
            media_root = Path(tmp)
            orphan = media_root / 'avatars' / '2026' / '05'
            orphan.mkdir(parents=True)
            orphan_file = orphan / 'old.jpg'
            orphan_file.write_bytes(b'orphan')

            with override_settings(MEDIA_ROOT=str(media_root)):
                result = cleanup_orphan_media(dry_run=True)
                self.assertEqual(result['orphan_count'], 1)
                self.assertTrue(orphan_file.exists())

                result = cleanup_orphan_media(dry_run=False)
                self.assertEqual(result['removed_count'], 1)
                self.assertFalse(orphan_file.exists())


class OrgStructureTreemapTests(TestCase):
    def setUp(self):
        from hrm.permissions import ROLE_DIRECTOR

        RoleModulePermission.objects.update_or_create(
            role=ROLE_DIRECTOR,
            defaults={'module_permissions': {MODULE_HRM: {'view': True, 'edit': True}}},
        )
        self.admin = User.objects.create_user(
            username='org_admin',
            password='test',
            is_staff=True,
        )
        Profile.objects.filter(user=self.admin).update(
            role=ROLE_DIRECTOR,
            full_name='Org Admin',
            is_employed=True,
        )
        self.dept = Department.objects.create(name='ORG-DEPT-A', sort_order=1)
        self.dept_b = Department.objects.create(name='ORG-DEPT-B', sort_order=2)
        Division.objects.create(name='ORG-DIV-1', department=self.dept, sort_order=1)
        Division.objects.create(name='ORG-DIV-2', department=self.dept, sort_order=2)
        Division.objects.create(name='ORG-DIV-ORPHAN', department=None, sort_order=3)
        self.client.force_login(self.admin)

    def test_org_structure_treemap_renders_hierarchy(self):
        response = self.client.get(reverse('org_structure'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'jp-org-tree-data')
        self.assertContains(response, 'subtitle')
        self.assertContains(response, 'ORG-DEPT-A')
        self.assertContains(response, 'ORG-DIV-1')
        self.assertContains(response, 'ORG-DIV-ORPHAN')
        self.assertContains(response, 'jp-org-tree-mount')
        self.assertContains(response, 'jp-org-tree-data')
        self.assertContains(response, 'ORG-DEPT-A')
        self.assertContains(response, 'org_tree.js')

    def test_division_form_rejects_duplicate_in_same_department(self):
        from hrm.forms import DivisionForm

        Division.objects.create(name='QC-SHARED', department=self.dept)
        form = DivisionForm({
            'department': self.dept.pk,
            'name': 'QC-SHARED',
            'sort_order': 0,
            'is_active': True,
        })
        self.assertFalse(form.is_valid())
        form_b = DivisionForm({
            'department': self.dept_b.pk,
            'name': 'QC-SHARED',
            'sort_order': 0,
            'is_active': True,
        })
        self.assertTrue(form_b.is_valid())

    def test_resolve_division_scoped_to_department(self):
        from hrm.choices import resolve_division

        Division.objects.create(name='QC-SCOPE', department=self.dept)
        div_b = Division.objects.create(name='QC-SCOPE', department=self.dept_b)
        div = resolve_division('QC-SCOPE', department=self.dept_b)
        self.assertEqual(div.pk, div_b.pk)
