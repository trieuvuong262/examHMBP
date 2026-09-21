from hrm.menu_permissions import menu_perm_context, user_can_access_menu
from kho_npl.stock_domain import (
    domain_from_request,
    kind_label,
    module_key_from_request,
    namespace_from_request,
)

_KIND_NAV_KEYS = {'materials', 'material_stock', 'stock_cards'}

NAV_ITEMS = [
    {'key': 'materials', 'url_name': 'material_list', 'label': 'Danh mục', 'icon': 'bi-tags'},
    {'key': 'material_stock', 'url_name': 'material_stock', 'label': 'Tồn kho', 'icon': 'bi-boxes'},
    {'key': 'stock_cards', 'url_name': 'stock_cards', 'label': 'Thẻ kho', 'icon': 'bi-grid-3x3-gap'},
    {'key': 'receipts', 'url_name': 'receipt_list', 'label': 'Phiếu nhập', 'icon': 'bi-box-arrow-in-down'},
    {'key': 'issues', 'url_name': 'issue_list', 'label': 'Phiếu xuất', 'icon': 'bi-box-arrow-up'},
    {'key': 'transfers', 'url_name': 'transfer_hub', 'label': 'Phiếu chuyển', 'icon': 'bi-arrow-left-right'},
    {'key': 'disposals', 'url_name': 'disposal_list', 'label': 'Phiếu hủy', 'icon': 'bi-trash3'},
    {'key': 'adjustments', 'url_name': 'adjustment_list', 'label': 'Phiếu kiểm kê', 'icon': 'bi-clipboard-check'},
    {'key': 'reports', 'url_name': 'report_hub', 'label': 'Báo cáo', 'icon': 'bi-file-earmark-bar-graph'},
    {'key': 'settings', 'url_name': 'settings_hub', 'label': 'Thiết lập', 'icon': 'bi-gear'},
]


def nav_context(active_key: str, user=None, request=None):
    ns = namespace_from_request(request)
    module = module_key_from_request(request)
    kind = kind_label(domain_from_request(request))
    items = [
        {
            **item,
            'url_name': f'{ns}:{item["url_name"]}',
            'label': f'{item["label"]} {kind}' if item['key'] in _KIND_NAV_KEYS else item['label'],
        }
        for item in NAV_ITEMS
    ]
    if user is not None and getattr(user, 'is_authenticated', False):
        items = [
            item for item in items
            if user_can_access_menu(user, module, item['key'])
        ]
    return {
        'nav_items': items,
        'active_nav': active_key,
    }


def perm_context(user, menu_key: str, request=None) -> dict:
    """Quyền UI theo menu con — khớp decorator và sidebar."""
    return menu_perm_context(user, module_key_from_request(request), menu_key)
