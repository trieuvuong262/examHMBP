from hrm.menu_permissions import menu_perm_context
from hrm.module_permissions import MODULE_KHO_NPL

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


def nav_context(active_key: str, user=None):
    from hrm.menu_permissions import user_can_access_menu

    items = NAV_ITEMS
    if user is not None and getattr(user, 'is_authenticated', False):
        items = [
            item for item in NAV_ITEMS
            if user_can_access_menu(user, MODULE_KHO_NPL, item['key'])
        ]
    return {
        'nav_items': items,
        'active_nav': active_key,
    }


def perm_context(user, menu_key: str) -> dict:
    """Quyền UI theo menu con — khớp decorator và sidebar."""
    return menu_perm_context(user, MODULE_KHO_NPL, menu_key)


def list_table_context(columns, table_id, *, row_count=None, page_obj=None):
    if row_count is None and page_obj is not None and hasattr(page_obj, 'paginator'):
        row_count = page_obj.paginator.count
    return {
        'list_columns': columns,
        'table_id': table_id,
        'row_count': row_count if row_count is not None else 0,
    }


def report_context():
    return {'report_items': report_hub_items()}
