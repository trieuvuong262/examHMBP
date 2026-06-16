from django.contrib.auth.models import User
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from hrm.forms import PermissionGroupPermissionForm
from hrm.group_permissions import get_user_module_perm, normalize_group_permissions
from hrm.menu_permissions import (
    get_effective_menu_perm,
    menu_perm_context,
    resolve_menu_from_request,
    user_can_access_menu,
    user_can_create_menu,
)
from hrm.middleware import DepartmentModuleAccessMiddleware
from hrm.models import PermissionGroup, Profile
from hrm.submenu_registry import get_module_submenus, perm_field_name


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

    def test_configured_group_denies_unknown_submenu(self):
        perm = get_effective_menu_perm(self.user, 'kho_npl', 'settings')
        self.assertFalse(perm['view'])
        self.assertFalse(perm['create'])

    def test_menu_access_checks(self):
        self.assertTrue(user_can_access_menu(self.user, 'kho_npl', 'overview'))
        self.assertTrue(user_can_access_menu(self.user, 'kho_npl', 'materials'))
        self.assertFalse(user_can_access_menu(self.user, 'kho_npl', 'receipts'))
        self.assertFalse(user_can_create_menu(self.user, 'kho_npl', 'receipts'))
        self.assertTrue(user_can_create_menu(self.user, 'kho_npl', 'materials'))

    def test_menu_perm_context_matches_menu(self):
        ctx = menu_perm_context(self.user, 'kho_npl', 'materials')
        self.assertTrue(ctx['can_create'])
        self.assertTrue(ctx['can_export'])
        ctx2 = menu_perm_context(self.user, 'kho_npl', 'receipts')
        self.assertFalse(ctx2['can_create'])
        self.assertFalse(ctx2['can_view'])

    def test_resolve_menu_from_request(self):
        module, menu = resolve_menu_from_request('/kho-npl/phieu-nhap/')
        self.assertEqual(module, 'kho_npl')
        self.assertEqual(menu, 'receipts')

        module, menu = resolve_menu_from_request('/kho-npl/danh-muc/them/')
        self.assertEqual(menu, 'materials')

        module, menu = resolve_menu_from_request('/nhat-ky/tro-ly-ai/')
        self.assertEqual(module, 'audit')
        self.assertEqual(menu, 'qa_assistant')

        module, menu = resolve_menu_from_request('/gop-y/danh-sach/')
        self.assertEqual(module, 'feedback')
        self.assertEqual(menu, 'list')

        module, menu = resolve_menu_from_request('/gop-y/42/')
        self.assertEqual(menu, 'list')

        module, menu = resolve_menu_from_request('/yeu-cau/de-xuat/99/')
        self.assertEqual(module, 'de_xuat')
        self.assertIsNone(menu)

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

    def test_middleware_allows_request_detail_without_my_menu(self):
        from django.contrib.messages.storage.fallback import FallbackStorage

        group = PermissionGroup.objects.create(
            name='Pending only',
            slug='pending-only-dx',
            module_permissions={
                'de_xuat': {
                    'view': True,
                    'menus': {
                        'pending': {'view': True, 'create': False, 'update': True, 'delete': False, 'export': False},
                    },
                },
            },
        )
        self._assign_group(group)

        factory = RequestFactory()
        request = factory.get('/yeu-cau/de-xuat/99/')
        request.user = self.user
        request.session = {}
        request._messages = FallbackStorage(request)

        middleware = DepartmentModuleAccessMiddleware(lambda req: HttpResponse('ok'))
        response = middleware(request)
        self.assertEqual(response.status_code, 200)

    def test_form_field_names_for_submenus(self):
        self.assertEqual(perm_field_name('view', 'kho_npl', 'materials'), 'view_kho_npl__materials')

    def test_form_round_trip_submenu_permissions(self):
        data = {}
        for sm in get_module_submenus('kho_npl'):
            for action in ('view', 'create', 'update', 'delete', 'export'):
                if sm['key'] == 'materials' and action in ('view', 'create', 'export'):
                    data[perm_field_name(action, 'kho_npl', sm['key'])] = 'on'
                elif sm['key'] == 'overview' and action == 'view':
                    data[perm_field_name(action, 'kho_npl', sm['key'])] = 'on'
        form = PermissionGroupPermissionForm(data)
        self.assertTrue(form.is_valid(), form.errors)
        perms = form.cleaned_permissions()['kho_npl']
        self.assertTrue(perms['menus']['materials']['create'])
        self.assertFalse(perms['menus']['receipts']['view'])
        self.assertFalse(perms['menus']['receipts']['create'])
