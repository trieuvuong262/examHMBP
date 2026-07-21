"""Quyen In (print) cho module San xuat."""

from django.test import SimpleTestCase

from hrm.group_permissions import (
    PERM_PRINT,
    empty_module_perm,
    module_permission_action_enabled,
    module_supports_print,
    normalize_module_perm,
)
from hrm.submenu_registry import parse_perm_field_name


class SanXuatPrintPermissionTests(SimpleTestCase):
    def test_only_san_xuat_supports_print(self):
        self.assertTrue(module_supports_print("san_xuat"))
        self.assertFalse(module_supports_print("hrm"))
        self.assertFalse(module_permission_action_enabled("hrm", PERM_PRINT))
        self.assertTrue(module_permission_action_enabled("san_xuat", PERM_PRINT))

    def test_normalize_keeps_print_for_san_xuat(self):
        perm = normalize_module_perm(
            {"view": True, "print": True},
            module_key="san_xuat",
        )
        self.assertTrue(perm[PERM_PRINT])
        other = normalize_module_perm(
            {"view": True, "print": True},
            module_key="hrm",
        )
        self.assertFalse(other[PERM_PRINT])

    def test_empty_perm_includes_print_key(self):
        empty = empty_module_perm()
        self.assertIn(PERM_PRINT, empty)
        self.assertFalse(empty[PERM_PRINT])

    def test_parse_perm_field_name_print(self):
        action, module, menu = parse_perm_field_name("print_san_xuat__mo")
        self.assertEqual(action, "print")
        self.assertEqual(module, "san_xuat")
        self.assertEqual(menu, "mo")