"""San xuat menu path rules vs submenu registry."""
from django.test import SimpleTestCase

from hrm.department_permission_templates import _san_xuat_menus
from hrm.menu_permissions import resolve_menu_from_request
from hrm.submenu_registry import MENU_PATH_RULES, MODULE_SAN_XUAT, MODULE_SUBMENUS


class SanXuatMenuPermissionTests(SimpleTestCase):
    def test_registry_keys_match_department_template(self):
        reg = {m["key"] for m in MODULE_SUBMENUS[MODULE_SAN_XUAT]}
        tpl = set(_san_xuat_menus(manager=True))
        self.assertEqual(reg, tpl)

    def test_every_registry_key_has_path_rule(self):
        reg = {m["key"] for m in MODULE_SUBMENUS[MODULE_SAN_XUAT]}
        rule_keys = {k for _p, m, k in MENU_PATH_RULES if m == MODULE_SAN_XUAT}
        # costing is legacy alias — may only appear in registry for UI
        missing = reg - rule_keys - {"costing"}
        self.assertFalse(missing, f"Missing path rules: {sorted(missing)}")

    def test_critical_paths_resolve_to_expected_menus(self):
        cases = [
            ("/san-xuat/bom/", "bom"),
            ("/san-xuat/nang-luc/", "capacity"),
            ("/san-xuat/shop-floor/", "shop_floor"),
            ("/san-xuat/dong-goi/", "packing"),
            ("/san-xuat/dong-goi/1/in/", "packing"),
            ("/san-xuat/thue-gia-cong/", "subcontract"),
            ("/san-xuat/ncr/", "ncr"),
            ("/san-xuat/ncr/1/in/", "ncr"),
            ("/san-xuat/truy-xuat/", "traceability"),
            ("/san-xuat/gia-thanh/thuc-te/", "actual_cost"),
            ("/san-xuat/gia-thanh/thuc-te/lsx/3/", "actual_cost"),
            ("/san-xuat/san-pham-nvl/", "products_nvl"),
            ("/san-xuat/chat-luong/canh-bao/", "qc"),
            ("/san-xuat/chat-luong/canh-bao/2/in/", "qc"),
            ("/san-xuat/bao-cao-van-hanh/", "ops_report"),
            ("/san-xuat/giao-viec/", "work_assign"),
            ("/san-xuat/dung-chuyen/", "downtime"),
            ("/san-xuat/luong-san-pham/", "piece_rate"),
            ("/san-xuat/staging/", "staging"),
            ("/san-xuat/catalog/", "unified_catalog"),
            ("/san-xuat/thiet-lap/", "general_settings"),
            ("/san-xuat/dieu-phoi/lenh-sx/1/in/", "mo"),
            ("/san-xuat/dieu-phoi/chay-lenh-moi/", "mo"),
            ("/san-xuat/ho-so/", "docs"),
            ("/san-xuat/cong-doan/", "ie"),
            ("/san-xuat/cong-doan/thu-vien/", "ie"),
            ("/san-xuat/cong-doan/xuat-excel/", "ie"),
            ("/san-xuat/cong-doan/mau-excel/", "ie"),
        ]
        for path, expected in cases:
            module, menu = resolve_menu_from_request(path)
            self.assertEqual(module, MODULE_SAN_XUAT, path)
            self.assertEqual(menu, expected, path)
