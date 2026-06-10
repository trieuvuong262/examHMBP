from hrm.module_permissions import (
    MODULE_KHO_NPL,
    user_can_create_module,
    user_can_delete_module,
    user_can_edit_module,
    user_can_export_module,
    user_can_update_module,
)

from kho_npl.reports_registry import report_hub_items

NAV_ITEMS = [
    {'key': 'overview', 'url_name': 'kho_npl:overview', 'label': 'Tổng quan tồn kho', 'icon': 'bi-speedometer2'},
    {'key': 'materials', 'url_name': 'kho_npl:material_list', 'label': 'Danh mục nguyên phụ liệu', 'icon': 'bi-tags'},
    {'key': 'material_stock', 'url_name': 'kho_npl:material_stock', 'label': 'Tồn kho nguyên phụ liệu', 'icon': 'bi-boxes'},
    {'key': 'stock_cards', 'url_name': 'kho_npl:stock_cards', 'label': 'Thẻ kho', 'icon': 'bi-grid-3x3-gap'},
    {'key': 'receipts', 'url_name': 'kho_npl:receipt_list', 'label': 'Phiếu nhập kho', 'icon': 'bi-box-arrow-in-down'},
    {'key': 'issues', 'url_name': 'kho_npl:issue_list', 'label': 'Phiếu xuất kho', 'icon': 'bi-box-arrow-up'},
    {'key': 'transfers', 'url_name': 'kho_npl:transfer_hub', 'label': 'Chuyển kho', 'icon': 'bi-arrow-left-right'},
    {'key': 'disposals', 'url_name': 'kho_npl:disposal_list', 'label': 'Phiếu hủy', 'icon': 'bi-trash3'},
    {'key': 'adjustments', 'url_name': 'kho_npl:adjustment_list', 'label': 'Điều chỉnh tồn kho', 'icon': 'bi-sliders'},
    {'key': 'stocktakes', 'url_name': 'kho_npl:stocktake_list', 'label': 'Kiểm kê kho', 'icon': 'bi-clipboard-check'},
    {'key': 'reports', 'url_name': 'kho_npl:report_hub', 'label': 'Báo cáo', 'icon': 'bi-file-earmark-bar-graph'},
    {'key': 'settings', 'url_name': 'kho_npl:settings_hub', 'label': 'Thiết lập', 'icon': 'bi-gear'},
]

def nav_context(active_key: str):
    return {
        'nav_items': NAV_ITEMS,
        'active_nav': active_key,
    }


def perm_context(user):
    return {
        'can_edit': user_can_edit_module(user, MODULE_KHO_NPL),
        'can_create': user_can_create_module(user, MODULE_KHO_NPL),
        'can_update': user_can_update_module(user, MODULE_KHO_NPL),
        'can_delete': user_can_delete_module(user, MODULE_KHO_NPL),
        'can_export': user_can_export_module(user, MODULE_KHO_NPL),
    }


def report_context():
    return {'report_items': report_hub_items()}
