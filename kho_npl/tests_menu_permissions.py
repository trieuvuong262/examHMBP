"""
Kiểm thử phân quyền menu / nhóm quyền — module Kho Nguyên Phụ Liệu.
"""

from django.contrib.auth.models import User
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse

from hrm.forms import PermissionGroupPermissionForm
from hrm.group_permissions import PERM_ACTIONS, empty_module_perm
from hrm.menu_permissions import (
    get_effective_menu_perm,
    menu_perm_context,
    resolve_menu_from_request,
    user_can_access_menu,
    user_can_create_menu,
    user_can_export_menu,
    user_can_update_menu,
)
from hrm.middleware import DepartmentModuleAccessMiddleware
from hrm.models import PermissionGroup, Profile
from hrm.module_permissions import MODULE_KHO_NPL, user_can_access_module
from hrm.permissions import ROLE_EMPLOYEE
from hrm.submenu_registry import get_module_submenus

from kho_npl.view_utils import NAV_ITEMS


def _menu_perm(**flags):
    base = empty_module_perm()
    for action in PERM_ACTIONS:
        base[action] = bool(flags.get(action, False))
    return base


def _kho_npl_group(*, menus: dict | None = None, **module_flags):
    """Tạo nhóm quyền Kho NPL — chỉ menus hoặc legacy module flags."""
    entry = {}
    if menus is not None:
        entry['menus'] = {
            menu_key: _menu_perm(**perms)
            for menu_key, perms in menus.items()
        }
    else:
        entry = _menu_perm(**module_flags)
    return PermissionGroup.objects.create(
        name='Kho NPL test',
        slug='kho-npl-test',
        module_permissions={MODULE_KHO_NPL: entry},
    )


class KhoNplMenuRegistryTests(TestCase):
    def test_nav_items_match_submenu_registry(self):
        registry_keys = {m['key'] for m in get_module_submenus(MODULE_KHO_NPL)}
        nav_keys = {item['key'] for item in NAV_ITEMS}
        self.assertEqual(registry_keys, nav_keys)

    def test_all_submenus_have_path_rules(self):
        from hrm.submenu_registry import MENU_PATH_RULES

        covered = {menu for _p, mod, menu in MENU_PATH_RULES if mod == MODULE_KHO_NPL}
        for sm in get_module_submenus(MODULE_KHO_NPL):
            with self.subTest(menu=sm['key']):
                self.assertIn(sm['key'], covered, f'Thiếu MENU_PATH_RULES cho {sm["key"]}')

    def test_resolve_menu_from_kho_npl_urls(self):
        cases = (
            ('/kho-npl/tong-quan/', 'overview'),
            ('/kho-npl/canh-bao/', 'overview'),
            ('/kho-npl/danh-muc/', 'materials'),
            ('/kho-npl/danh-muc/them/', 'materials'),
            ('/kho-npl/ton-kho-npl/', 'material_stock'),
            ('/kho-npl/the-kho/', 'stock_cards'),
            ('/kho-npl/phieu-nhap/', 'receipts'),
            ('/kho-npl/phieu-xuat/', 'issues'),
            ('/kho-npl/chuyen-kho/', 'transfers'),
            ('/kho-npl/phieu-huy/', 'disposals'),
            ('/kho-npl/dieu-chinh/', 'adjustments'),
            ('/kho-npl/kiem-ke/', 'stocktakes'),
            ('/kho-npl/kiem-ke/xuat-excel/', 'stocktakes'),
            ('/kho-npl/bao-cao/', 'reports'),
            ('/kho-npl/thiet-lap/', 'settings'),
        )
        for path, expected_menu in cases:
            with self.subTest(path=path):
                module, menu = resolve_menu_from_request(path)
                self.assertEqual(module, MODULE_KHO_NPL)
                self.assertEqual(menu, expected_menu)


class KhoNplMenuPermissionMatrixTests(TestCase):
    MENU_PAGES = {
        'overview': 'kho_npl:overview',
        'materials': 'kho_npl:material_list',
        'material_stock': 'kho_npl:material_stock',
        'stock_cards': 'kho_npl:stock_cards',
        'receipts': 'kho_npl:receipt_list',
        'issues': 'kho_npl:issue_list',
        'transfers': 'kho_npl:transfer_hub',
        'disposals': 'kho_npl:disposal_list',
        'adjustments': 'kho_npl:adjustment_list',
        'stocktakes': 'kho_npl:stocktake_list',
        'reports': 'kho_npl:report_hub',
        'settings': 'kho_npl:settings_hub',
    }

    EXPORT_URLS = {
        'overview': 'kho_npl:overview_export',
        'materials': 'kho_npl:material_export',
        'material_stock': 'kho_npl:material_stock_export',
        'stock_cards': 'kho_npl:stock_cards_export',
        'stocktakes': 'kho_npl:stocktake_list_export',
        'reports': 'kho_npl:report_stock_export',
    }

    CREATE_URLS = {
        'materials': 'kho_npl:material_create',
        'receipts': 'kho_npl:receipt_create',
        'issues': 'kho_npl:issue_create',
        'transfers': 'kho_npl:transfer_create',
        'disposals': 'kho_npl:disposal_create',
        'adjustments': 'kho_npl:adjustment_create',
        'stocktakes': 'kho_npl:stocktake_create',
    }

    def setUp(self):
        self.user = User.objects.create_user(username='npl_matrix', password='test')
        Profile.objects.filter(user=self.user).update(role=ROLE_EMPLOYEE, is_employed=True)
        self.client.force_login(self.user)

    def _assign(self, group):
        profile = Profile.objects.get(user=self.user)
        profile.permission_group = group
        profile.save(update_fields=['permission_group'])
        self.user.refresh_from_db()

    def test_single_menu_view_only(self):
        group = _kho_npl_group(menus={
            'stocktakes': {'view': True},
            'materials': {'view': False},
            'receipts': {'view': False},
        })
        self._assign(group)

        self.assertTrue(user_can_access_module(self.user, MODULE_KHO_NPL))
        self.assertTrue(user_can_access_menu(self.user, MODULE_KHO_NPL, 'stocktakes'))
        self.assertFalse(user_can_access_menu(self.user, MODULE_KHO_NPL, 'materials'))

        self.assertEqual(self.client.get(reverse('kho_npl:stocktake_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('kho_npl:material_list')).status_code, 302)

    def test_stocktakes_export_requires_menu_export(self):
        group = _kho_npl_group(menus={
            'stocktakes': {'view': True, 'export': False},
        })
        self._assign(group)
        self.assertEqual(self.client.get(reverse('kho_npl:stocktake_list_export')).status_code, 302)

        group.module_permissions = {
            MODULE_KHO_NPL: {'menus': {'stocktakes': _menu_perm(view=True, export=True)}},
        }
        group.save(update_fields=['module_permissions'])
        self._assign(group)
        resp = self.client.get(reverse('kho_npl:stocktake_list_export'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('spreadsheetml', resp['Content-Type'])

    def test_stocktakes_create_requires_menu_create(self):
        group = _kho_npl_group(menus={'stocktakes': {'view': True, 'create': False}})
        self._assign(group)
        self.assertEqual(self.client.get(reverse('kho_npl:stocktake_create')).status_code, 302)

        group.module_permissions = {
            MODULE_KHO_NPL: {'menus': {'stocktakes': _menu_perm(view=True, create=True)}},
        }
        group.save(update_fields=['module_permissions'])
        self.assertEqual(self.client.get(reverse('kho_npl:stocktake_create')).status_code, 200)

    def test_legacy_full_module_inherits_all_submenus(self):
        group = _kho_npl_group(view=True, create=True, update=True, delete=True, export=True)
        self._assign(group)
        for menu_key in self.MENU_PAGES:
            with self.subTest(menu=menu_key):
                self.assertTrue(
                    user_can_access_menu(self.user, MODULE_KHO_NPL, menu_key),
                    menu_key,
                )

    def test_configured_unknown_submenu_denied(self):
        group = _kho_npl_group(menus={'materials': {'view': True}})
        self._assign(group)
        perm = get_effective_menu_perm(self.user, MODULE_KHO_NPL, 'settings')
        self.assertFalse(perm['view'])

    def test_menu_perm_context_for_stocktakes(self):
        group = _kho_npl_group(menus={
            'stocktakes': {'view': True, 'create': True, 'update': True, 'export': True},
        })
        self._assign(group)
        ctx = menu_perm_context(self.user, MODULE_KHO_NPL, 'stocktakes')
        self.assertTrue(ctx['can_view'])
        self.assertTrue(ctx['can_create'])
        self.assertTrue(ctx['can_update'])
        self.assertTrue(ctx['can_export'])

    def test_sidebar_hides_denied_menus(self):
        group = _kho_npl_group(menus={
            'overview': {'view': True},
            'stocktakes': {'view': True},
            'receipts': {'view': False},
            'materials': {'view': False},
        })
        self._assign(group)
        response = self.client.get(reverse('kho_npl:stocktake_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Phiếu kiểm kê')
        self.assertNotContains(response, reverse('kho_npl:receipt_list'))
        self.assertNotContains(response, reverse('kho_npl:material_list'))

    def test_nav_context_filters_internal_tabs(self):
        from kho_npl.view_utils import nav_context

        group = _kho_npl_group(menus={
            'stocktakes': {'view': True},
            'materials': {'view': False},
        })
        self._assign(group)
        ctx = nav_context('stocktakes', user=self.user)
        keys = [item['key'] for item in ctx['nav_items']]
        self.assertIn('stocktakes', keys)
        self.assertNotIn('materials', keys)

    def test_middleware_blocks_denied_menu(self):
        from django.contrib.messages.storage.fallback import FallbackStorage

        group = _kho_npl_group(menus={
            'stocktakes': {'view': True},
            'receipts': {'view': False},
        })
        self._assign(group)

        factory = RequestFactory()
        request = factory.get('/kho-npl/phieu-nhap/')
        request.user = self.user
        request.session = {}
        request._messages = FallbackStorage(request)

        middleware = DepartmentModuleAccessMiddleware(lambda req: HttpResponse('ok'))
        response = middleware(request)
        self.assertEqual(response.status_code, 302)

    def test_permission_form_includes_all_kho_npl_submenus(self):
        form = PermissionGroupPermissionForm()
        rows = [r for r in form.module_rows() if r['key'] == MODULE_KHO_NPL]
        self.assertEqual(len(rows), 1)
        submenu_keys = {sm['key'] for sm in rows[0]['submenus']}
        self.assertEqual(submenu_keys, {m['key'] for m in get_module_submenus(MODULE_KHO_NPL)})
        self.assertIn('stocktakes', submenu_keys)

    def test_each_menu_page_respects_view_flag(self):
        allowed = {'materials', 'stocktakes'}
        menus = {
            key: {'view': key in allowed}
            for key in self.MENU_PAGES
        }
        self._assign(_kho_npl_group(menus=menus))

        for menu_key, url_name in self.MENU_PAGES.items():
            with self.subTest(menu=menu_key):
                response = self.client.get(reverse(url_name))
                if menu_key in allowed:
                    self.assertEqual(response.status_code, 200, url_name)
                else:
                    self.assertEqual(response.status_code, 302, url_name)

    def test_export_urls_respect_menu_export(self):
        menus = {
            'stocktakes': {'view': True, 'export': True},
            'materials': {'view': True, 'export': False},
        }
        self._assign(_kho_npl_group(menus=menus))

        self.assertEqual(
            self.client.get(reverse(self.EXPORT_URLS['stocktakes'])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse(self.EXPORT_URLS['materials'])).status_code,
            302,
        )

    def test_create_urls_respect_menu_create(self):
        menus = {
            'stocktakes': {'view': True, 'create': True},
            'receipts': {'view': True, 'create': False},
        }
        self._assign(_kho_npl_group(menus=menus))

        self.assertFalse(user_can_create_menu(self.user, MODULE_KHO_NPL, 'receipts'))
        self.assertTrue(user_can_create_menu(self.user, MODULE_KHO_NPL, 'stocktakes'))
        self.assertEqual(self.client.get(reverse(self.CREATE_URLS['stocktakes'])).status_code, 200)
        self.assertEqual(self.client.get(reverse(self.CREATE_URLS['receipts'])).status_code, 302)

    def test_update_flag_on_stocktake_count(self):
        group = _kho_npl_group(menus={'stocktakes': {'view': True, 'update': False}})
        self._assign(group)
        self.assertFalse(user_can_update_menu(self.user, MODULE_KHO_NPL, 'stocktakes'))
