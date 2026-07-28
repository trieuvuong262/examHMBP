from hrm.menu_permissions import menu_perm_context
from hrm.module_permissions import MODULE_KHO_SAN_PHAM

NAV_ITEMS = [
    {'key': 'products', 'url_name': 'kho_san_pham:product_list', 'label': 'Danh mục', 'icon': 'bi-tags'},
]


def nav_context(active_key: str, user=None):
    from hrm.menu_permissions import user_can_access_menu

    items = NAV_ITEMS
    if user is not None and getattr(user, 'is_authenticated', False):
        items = [
            item for item in NAV_ITEMS
            if user_can_access_menu(user, MODULE_KHO_SAN_PHAM, item['key'])
        ]
    return {
        'nav_items': items,
        'active_nav': active_key,
    }


def perm_context(user, menu_key: str) -> dict:
    return menu_perm_context(user, MODULE_KHO_SAN_PHAM, menu_key)
