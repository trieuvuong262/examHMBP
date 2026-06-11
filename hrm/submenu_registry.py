"""
Registry menu con — khớp sidebar và URL.

Mỗi module có thể có danh sách submenu; path rules dùng để resolve menu từ request.
"""

from hrm.module_permissions import (
    MODULE_AUDIT,
    MODULE_DE_XUAT,
    MODULE_DOCUMENTS,
    MODULE_EQUIPMENT,
    MODULE_FEEDBACK,
    MODULE_HO_TRO,
    MODULE_KHO_NPL,
    MODULE_KIOTVIET,
    MODULE_REPORTS,
    MODULE_TASKS,
)

# {module_key: [{key, label, icon}, ...]}
MODULE_SUBMENUS: dict[str, list[dict]] = {
    MODULE_REPORTS: [
        {'key': 'daily', 'label': 'Báo cáo ngày', 'icon': 'bi-calendar-day'},
        {'key': 'weekly', 'label': 'Báo cáo tuần', 'icon': 'bi-calendar-week'},
    ],
    MODULE_TASKS: [
        {'key': 'personal', 'label': 'Giao việc cá nhân', 'icon': 'bi-person-check'},
        {'key': 'project', 'label': 'Dự án nội bộ', 'icon': 'bi-kanban'},
        {'key': 'cross_dept', 'label': 'Dự án liên phòng ban', 'icon': 'bi-diagram-3'},
    ],
    MODULE_DE_XUAT: [
        {'key': 'my', 'label': 'Yêu cầu của tôi', 'icon': 'bi-person-lines-fill'},
        {'key': 'pending', 'label': 'Chờ xử lý', 'icon': 'bi-inbox-fill'},
        {'key': 'create', 'label': 'Gửi đề xuất', 'icon': 'bi-plus-circle'},
        {'key': 'catalog', 'label': 'Danh mục định kỳ', 'icon': 'bi-journal-text'},
    ],
    MODULE_HO_TRO: [
        {'key': 'my', 'label': 'Yêu cầu của tôi', 'icon': 'bi-person-lines-fill'},
        {'key': 'pending', 'label': 'Chờ duyệt', 'icon': 'bi-inbox-fill'},
        {'key': 'create', 'label': 'Gửi yêu cầu hỗ trợ', 'icon': 'bi-plus-circle'},
    ],
    MODULE_EQUIPMENT: [
        {'key': 'it', 'label': 'Quản lý thiết bị IT', 'icon': 'bi-pc-display-horizontal'},
        {'key': 'production', 'label': 'Quản lý thiết bị sản xuất', 'icon': 'bi-gear-wide-connected'},
    ],
    MODULE_FEEDBACK: [
        {'key': 'create', 'label': 'Gửi góp ý', 'icon': 'bi-plus-circle'},
        {'key': 'list', 'label': 'Danh sách góp ý', 'icon': 'bi-inbox-fill'},
    ],
    MODULE_KHO_NPL: [
        {'key': 'overview', 'label': 'Tổng quan', 'icon': 'bi-speedometer2'},
        {'key': 'materials', 'label': 'Danh mục', 'icon': 'bi-tags'},
        {'key': 'material_stock', 'label': 'Tồn kho', 'icon': 'bi-boxes'},
        {'key': 'stock_cards', 'label': 'Thẻ kho', 'icon': 'bi-grid-3x3-gap'},
        {'key': 'receipts', 'label': 'Phiếu nhập', 'icon': 'bi-box-arrow-in-down'},
        {'key': 'issues', 'label': 'Phiếu xuất', 'icon': 'bi-box-arrow-up'},
        {'key': 'transfers', 'label': 'Phiếu chuyển', 'icon': 'bi-arrow-left-right'},
        {'key': 'disposals', 'label': 'Phiếu hủy', 'icon': 'bi-trash3'},
        {'key': 'adjustments', 'label': 'Phiếu điều chỉnh', 'icon': 'bi-sliders'},
        {'key': 'stocktakes', 'label': 'Phiếu kiểm kê', 'icon': 'bi-clipboard-check'},
        {'key': 'reports', 'label': 'Báo cáo', 'icon': 'bi-file-earmark-bar-graph'},
        {'key': 'settings', 'label': 'Thiết lập', 'icon': 'bi-gear'},
    ],
    MODULE_KIOTVIET: [
        {'key': 'customers', 'label': 'Tra cứu khách hàng', 'icon': 'bi-person-vcard'},
        {'key': 'orders', 'label': 'Đơn đặt hàng', 'icon': 'bi-cart-check'},
        {'key': 'invoices', 'label': 'Hóa đơn', 'icon': 'bi-receipt'},
        {'key': 'products', 'label': 'Hàng hoá', 'icon': 'bi-box-seam'},
        {'key': 'stock', 'label': 'Tồn kho', 'icon': 'bi-boxes'},
        {'key': 'purchases', 'label': 'Phiếu nhập', 'icon': 'bi-box-arrow-in-down'},
    ],
    MODULE_DOCUMENTS: [
        {'key': 'browse', 'label': 'Tài liệu', 'icon': 'bi-folder2-open'},
        {'key': 'qa', 'label': 'Hỏi đáp', 'icon': 'bi-chat-dots-fill'},
    ],
    MODULE_AUDIT: [
        {'key': 'login_security', 'label': 'Bảo mật đăng nhập', 'icon': 'bi-shield-lock'},
        {'key': 'logs', 'label': 'Nhật ký thao tác', 'icon': 'bi-journal-check'},
        {'key': 'backup', 'label': 'Backup lên NAS', 'icon': 'bi-cloud-arrow-up'},
        {'key': 'kiotviet_sync', 'label': 'Đồng bộ KiotViet', 'icon': 'bi-arrow-repeat'},
        {'key': 'nas_links', 'label': 'Cập nhật link NAS', 'icon': 'bi-hdd-network'},
    ],
}

# (path_prefix, module_key, menu_key) — prefix dài / cụ thể trước
MENU_PATH_RULES: list[tuple[str, str, str]] = [
    # Báo cáo
    ('/reports/team/weekly', MODULE_REPORTS, 'weekly'),
    ('/reports/weekly', MODULE_REPORTS, 'weekly'),
    ('/reports/team', MODULE_REPORTS, 'daily'),
    ('/reports/today', MODULE_REPORTS, 'daily'),
    ('/reports/my', MODULE_REPORTS, 'daily'),
    ('/reports/copy-yesterday', MODULE_REPORTS, 'daily'),
    ('/reports/copy-prev-week', MODULE_REPORTS, 'weekly'),
    ('/reports/ckeditor5-upload', MODULE_REPORTS, 'daily'),
    # Công việc
    ('/cong-viec/lien-phong-ban', MODULE_TASKS, 'cross_dept'),
    ('/cong-viec/du-an', MODULE_TASKS, 'project'),
    ('/cong-viec/ca-nhan', MODULE_TASKS, 'personal'),
    # Đề xuất
    ('/yeu-cau/de-xuat/danh-muc-dinh-ky', MODULE_DE_XUAT, 'catalog'),
    ('/yeu-cau/de-xuat/tao', MODULE_DE_XUAT, 'create'),
    ('/yeu-cau/de-xuat/cho-xu-ly', MODULE_DE_XUAT, 'pending'),
    ('/yeu-cau/de-xuat/theo-doi', MODULE_DE_XUAT, 'pending'),
    ('/yeu-cau/de-xuat/cua-toi', MODULE_DE_XUAT, 'my'),
    ('/yeu-cau/danh-muc-dinh-ky', MODULE_DE_XUAT, 'catalog'),
    ('/yeu-cau/tao', MODULE_DE_XUAT, 'create'),
    ('/yeu-cau/cho-xu-ly', MODULE_DE_XUAT, 'pending'),
    ('/yeu-cau/cua-toi', MODULE_DE_XUAT, 'my'),
    # Hỗ trợ
    ('/yeu-cau/ho-tro/tao', MODULE_HO_TRO, 'create'),
    ('/yeu-cau/ho-tro/cho-xu-ly', MODULE_HO_TRO, 'pending'),
    ('/yeu-cau/ho-tro/theo-doi', MODULE_HO_TRO, 'pending'),
    ('/yeu-cau/ho-tro/cua-toi', MODULE_HO_TRO, 'my'),
    ('/yeu-cau/sua-it', MODULE_HO_TRO, 'create'),
    # Thiết bị
    ('/thiet-bi/san-xuat', MODULE_EQUIPMENT, 'production'),
    ('/thiet-bi/it', MODULE_EQUIPMENT, 'it'),
    # Góp ý
    ('/gop-y/danh-sach', MODULE_FEEDBACK, 'list'),
    ('/gop-y/tao', MODULE_FEEDBACK, 'create'),
    # Kho NPL
    ('/kho-npl/thiet-lap', MODULE_KHO_NPL, 'settings'),
    ('/kho-npl/bao-cao', MODULE_KHO_NPL, 'reports'),
    ('/kho-npl/kiem-ke', MODULE_KHO_NPL, 'stocktakes'),
    ('/kho-npl/dieu-chinh', MODULE_KHO_NPL, 'adjustments'),
    ('/kho-npl/phieu-huy', MODULE_KHO_NPL, 'disposals'),
    ('/kho-npl/chuyen-kho', MODULE_KHO_NPL, 'transfers'),
    ('/kho-npl/phieu-xuat', MODULE_KHO_NPL, 'issues'),
    ('/kho-npl/phieu-nhap', MODULE_KHO_NPL, 'receipts'),
    ('/kho-npl/the-kho', MODULE_KHO_NPL, 'stock_cards'),
    ('/kho-npl/ton-kho-npl', MODULE_KHO_NPL, 'material_stock'),
    ('/kho-npl/danh-muc', MODULE_KHO_NPL, 'materials'),
    ('/kho-npl/canh-bao', MODULE_KHO_NPL, 'overview'),
    ('/kho-npl/tong-quan', MODULE_KHO_NPL, 'overview'),
    # KiotViet
    ('/kiotviet/phieu-nhap', MODULE_KIOTVIET, 'purchases'),
    ('/kiotviet/ton-kho', MODULE_KIOTVIET, 'stock'),
    ('/kiotviet/hang-hoa', MODULE_KIOTVIET, 'products'),
    ('/kiotviet/hoa-don', MODULE_KIOTVIET, 'invoices'),
    ('/kiotviet/don-dat-hang', MODULE_KIOTVIET, 'orders'),
    ('/kiotviet/khach-hang', MODULE_KIOTVIET, 'customers'),
    # Tài liệu
    ('/tai-lieu/hoi-dap', MODULE_DOCUMENTS, 'qa'),
    ('/tai-lieu/admin', MODULE_DOCUMENTS, 'browse'),
    ('/tai-lieu/file', MODULE_DOCUMENTS, 'browse'),
    ('/tai-lieu/', MODULE_DOCUMENTS, 'browse'),
    # Quản trị hệ thống
    ('/nhat-ky/bao-mat-dang-nhap', MODULE_AUDIT, 'login_security'),
    ('/nhat-ky/backup', MODULE_AUDIT, 'backup'),
    ('/nhat-ky/kiotviet-sync', MODULE_AUDIT, 'kiotviet_sync'),
    ('/nhat-ky/nas-links', MODULE_AUDIT, 'nas_links'),
    ('/nhat-ky/xuat-excel', MODULE_AUDIT, 'logs'),
    ('/nhat-ky/user/', MODULE_AUDIT, 'logs'),
    ('/nhat-ky/', MODULE_AUDIT, 'logs'),
]

MENU_FIELD_SEP = '__'


def module_has_submenus(module_key: str) -> bool:
    return bool(MODULE_SUBMENUS.get(module_key))


def get_module_submenus(module_key: str) -> list[dict]:
    return list(MODULE_SUBMENUS.get(module_key, []))


def get_menu_label(module_key: str, menu_key: str) -> str:
    for item in get_module_submenus(module_key):
        if item['key'] == menu_key:
            return item['label']
    return menu_key


def perm_field_name(action: str, module_key: str, menu_key: str | None = None) -> str:
    if menu_key:
        return f'{action}_{module_key}{MENU_FIELD_SEP}{menu_key}'
    return f'{action}_{module_key}'


def parse_perm_field_name(field_name: str) -> tuple[str, str, str | None]:
    """Trả về (action, module_key, menu_key|None)."""
    for action in ('view', 'create', 'update', 'delete', 'export'):
        prefix = f'{action}_'
        if not field_name.startswith(prefix):
            continue
        rest = field_name[len(prefix):]
        if MENU_FIELD_SEP in rest:
            module_key, menu_key = rest.split(MENU_FIELD_SEP, 1)
            return action, module_key, menu_key
        return action, rest, None
    raise ValueError(f'Invalid permission field: {field_name}')
