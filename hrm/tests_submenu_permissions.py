from django.contrib.auth.models import User
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from hrm.group_permissions import get_user_module_perm, normalize_group_permissions
from hrm.permissions import get_profile
from hrm.menu_permissions import (
    get_effective_menu_perm,
    resolve_menu_from_request,
    user_can_access_menu,
)
from hrm.middleware import DepartmentModuleAccessMiddleware
from hrm.models import PermissionGroup, Profile
from hrm.submenu_registry import perm_field_name


class SubmenuPermissionTests(TestCase):
    def _assign_group(self, group):
        profile = Profile.objects.get(user=self.user)
        profile.permission_group = group
        profile.save(update_fields=['permission_group'])
        self.user.refresh_from_db()

    def setUp(self):
        self.user = User.objects.create_user(username='submenu_user', password='x')
        profile = Profile.objects.get(user=self.user)
        profile.full_name = 'Submenu User'
        profile.save(update_fields=['full_name'])
        self.group = PermissionGroup.objects.create(
            name='Kho hạn chế',
            slug='kho-han-che',
            module_permissions={
                'kho_npl': {
                    'view': True,
                    'create': False,
                    'update': False,
                    'delete': False,
                    'export': False,
                    'menus': {
                        'overview': {'view': True, 'create': False, 'update': False, 'delete': False, 'export': False},
                        'materials': {'view': True, 'create': True, 'update': True, 'delete': False, 'export': True},
                        'receipts': {'view': False, 'create': False, 'update': False, 'delete': False, 'export': False},
                    },
                },
            },
        )
        self._assign_group(self.group)

    def test_normalize_preserves_menus_and_aggregates_module(self):
        perms = normalize_group_permissions(self.group.module_permissions)
        kho = perms['kho_npl']
        self.assertTrue(kho['view'])
        self.assertTrue(kho['create'])
        self.assertTrue(kho['export'])
        self.assertIn('menus', kho)
        self.assertFalse(kho['menus']['receipts']['view'])

    def test_legacy_group_inherits_module_to_submenus(self):
        legacy_group = PermissionGroup.objects.create(
            name='Legacy full kho',
            slug='legacy-full-kho',
            module_permissions={
                'kho_npl': {'view': True, 'create': True, 'update': True, 'delete': True, 'export': True},
            },
        )
        self._assign_group(legacy_group)

        perm = get_effective_menu_perm(self.user, 'kho_npl', 'disposals')
        self.assertTrue(perm['view'])
        self.assertTrue(perm['create'])

    def test_menu_access_checks(self):
        profile = get_profile(self.user)
        self.assertEqual(profile.permission_group_id, self.group.pk)
        kho_perm = get_user_module_perm(self.user, 'kho_npl')
        self.assertIn('menus', kho_perm)
        self.assertFalse(kho_perm['menus']['receipts']['view'])

        self.assertTrue(user_can_access_menu(self.user, 'kho_npl', 'overview'))
        self.assertTrue(user_can_access_menu(self.user, 'kho_npl', 'materials'))
        self.assertFalse(user_can_access_menu(self.user, 'kho_npl', 'receipts'))

    def test_resolve_menu_from_request(self):
        module, menu = resolve_menu_from_request('/kho-npl/phieu-nhap/')
        self.assertEqual(module, 'kho_npl')
        self.assertEqual(menu, 'receipts')

        module, menu = resolve_menu_from_request('/kho-npl/danh-muc/them/')
        self.assertEqual(menu, 'materials')

    def test_middleware_blocks_denied_submenu(self):
        from django.contrib.messages.storage.fallback import FallbackStorage

        factory = RequestFactory()
        request = factory.get('/kho-npl/phieu-nhap/')
        request.user = self.user
        request.session = {}
        request._messages = FallbackStorage(request)

        middleware = DepartmentModuleAccessMiddleware(lambda req: HttpResponse('ok'))
        response = middleware(request)
        self.assertEqual(response.status_code, 302)

    def test_form_field_names_for_submenus(self):
        self.assertEqual(perm_field_name('view', 'kho_npl', 'materials'), 'view_kho_npl__materials')
