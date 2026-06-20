"""
Registry menu con — khớp sidebar và URL.

Mỗi module có thể có danh sách submenu; path rules dùng để resolve menu từ request.
"""

from hrm.module_permissions import (
    MODULE_ASSESSMENT,
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
    MODULE_TRAINING,
    MODULE_UTILITIES,
)

# {module_key: [{key, label, icon}, ...]}
MODULE_SUBMENUS: dict[str, list[dict]] = {
    MODULE_TRAINING: [
        {'key': 'lessons', 'label': 'Bài học', 'icon': 'bi-book-fill', 'perm_view_only': True},
        {'key': 'manage', 'label': 'Quản lý bài học', 'icon': 'bi-journal-bookmark-fill'},
    ],
    MODULE_ASSESSMENT: [
        {'key': 'exams', 'label': 'Kiểm tra', 'icon': 'bi-journal-check', 'perm_view_only': True},
        {'key': 'manage', 'label': 'Quản lý kiểm tra', 'icon': 'bi-ui-checks-grid'},
    ],
    MODULE_REPORTS: [
        {'key': 'daily_cn', 'label': 'Báo cáo ngày (SX)', 'icon': 'bi-calendar-day'},
        {'key': 'daily_cn_detail', 'label': 'Quản lý báo cáo (SX)', 'icon': 'bi-people-fill'},
        {'key': 'daily_vp', 'label': 'Báo cáo ngày (VP)', 'icon': 'bi-calendar-day'},
        {'key': 'daily_vp_detail', 'label': 'Quản lý báo cáo (VP)', 'icon': 'bi-people-fill'},
        {'key': 'weekly_cn', 'label': 'Báo cáo tuần (SX)', 'icon': 'bi-calendar-week'},
        {'key': 'weekly_cn_detail', 'label': 'Quản lý báo cáo tuần (SX)', 'icon': 'bi-people-fill'},
        {'key': 'weekly_vp', 'label': 'Báo cáo tuần (VP)', 'icon': 'bi-calendar-week'},
        {'key': 'weekly_vp_detail', 'label': 'Quản lý báo cáo tuần (VP)', 'icon': 'bi-people-fill'},
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
        {'key': 'it', 'label': 'IT', 'icon': 'bi-pc-display-horizontal'},
        {'key': 'production', 'label': 'Sản xuất', 'icon': 'bi-gear-wide-connected'},
    ],
    MODULE_FEEDBACK: [
        {'key': 'create', 'label': 'Gửi góp ý', 'icon': 'bi-plus-circle'},
        {'key': 'list', 'label': 'Danh sách góp ý', 'icon': 'bi-inbox-fill'},
    ],
    MODULE_UTILITIES: [
        {'key': 'meal_ordering', 'label': 'Đặt cơm', 'icon': 'bi-cup-hot'},
        {'key': 'salary_advance', 'label': 'Ứng lương', 'icon': 'bi-cash-coin'},
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
        {'key': 'qa_assistant', 'label': 'Trợ lý AI', 'icon': 'bi-stars'},
    ],
}

# (path_prefix, module_key, menu_key) — prefix dài / cụ thể trước
MENU_PATH_RULES: list[tuple[str, str, str]] = [
    # Đào tạo — quản lý
    ('/training/admin/', MODULE_TRAINING, 'manage'),
    ('/training/api/categories/', MODULE_TRAINING, 'manage'),
    ('/training/', MODULE_TRAINING, 'lessons'),
    # Kiểm tra — quản lý
    ('/dashboard/exam/', MODULE_ASSESSMENT, 'manage'),
    ('/dashboard/results/', MODULE_ASSESSMENT, 'manage'),
    ('/dashboard/competency/', MODULE_ASSESSMENT, 'manage'),
    ('/dashboard/submission/', MODULE_ASSESSMENT, 'manage'),
    ('/exams/', MODULE_ASSESSMENT, 'exams'),
    # Báo cáo — SX (sản xuất)
    ('/reports/sx/team', MODULE_REPORTS, 'daily_cn_detail'),
    ('/reports/sx/my', MODULE_REPORTS, 'daily_cn'),
    ('/reports/sx/copy-yesterday', MODULE_REPORTS, 'daily_cn'),
    ('/reports/sx/today', MODULE_REPORTS, 'daily_cn'),
    # Legacy /reports/cn/ → redirect sang sx
    ('/reports/cn/team', MODULE_REPORTS, 'daily_cn_detail'),
    ('/reports/cn/my', MODULE_REPORTS, 'daily_cn'),
    ('/reports/cn/copy-yesterday', MODULE_REPORTS, 'daily_cn'),
    ('/reports/cn/today', MODULE_REPORTS, 'daily_cn'),
    # Báo cáo — VP (văn phòng)
    ('/reports/vp/team', MODULE_REPORTS, 'daily_vp_detail'),
    ('/reports/vp/my', MODULE_REPORTS, 'daily_vp'),
    ('/reports/vp/copy-yesterday', MODULE_REPORTS, 'daily_vp'),
    ('/reports/vp/today', MODULE_REPORTS, 'daily_vp'),
    ('/reports/vp/ckeditor5-upload', MODULE_REPORTS, 'daily_vp'),
    # Báo cáo tuần — SX
    ('/reports/sx/team/weekly', MODULE_REPORTS, 'weekly_cn_detail'),
    ('/reports/sx/weekly', MODULE_REPORTS, 'weekly_cn'),
    ('/reports/sx/copy-prev-week', MODULE_REPORTS, 'weekly_cn'),
    # Báo cáo tuần — VP
    ('/reports/vp/team/weekly', MODULE_REPORTS, 'weekly_vp_detail'),
    ('/reports/vp/weekly', MODULE_REPORTS, 'weekly_vp'),
    ('/reports/vp/copy-prev-week', MODULE_REPORTS, 'weekly_vp'),
    # Legacy (giữ tương thích URL cũ)
    ('/reports/team/weekly', MODULE_REPORTS, 'weekly_cn_detail'),
    ('/reports/weekly', MODULE_REPORTS, 'weekly_cn'),
    ('/reports/team', MODULE_REPORTS, 'daily_cn_detail'),
    ('/reports/today', MODULE_REPORTS, 'daily_cn'),
    ('/reports/my', MODULE_REPORTS, 'daily_cn'),
    ('/reports/copy-yesterday', MODULE_REPORTS, 'daily_cn'),
    ('/reports/copy-prev-week', MODULE_REPORTS, 'weekly_cn'),
    ('/reports/ckeditor5-upload', MODULE_REPORTS, 'daily_vp'),
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
    # Tiện ích
    ('/tien-ich/ung-luong', MODULE_UTILITIES, 'salary_advance'),
    ('/tien-ich/dat-com', MODULE_UTILITIES, 'meal_ordering'),
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
    # Tiện ích
    ('/tien-ich/ung-luong', MODULE_UTILITIES, 'salary_advance'),
    ('/tien-ich/dat-com', MODULE_UTILITIES, 'meal_ordering'),
    # Tài liệu
    ('/tai-lieu/hoi-dap', MODULE_DOCUMENTS, 'qa'),
    ('/tai-lieu/admin', MODULE_DOCUMENTS, 'browse'),
    ('/tai-lieu/file', MODULE_DOCUMENTS, 'browse'),
    ('/tai-lieu/', MODULE_DOCUMENTS, 'browse'),
    # Quản trị hệ thống
    ('/nhat-ky/tro-ly-ai', MODULE_AUDIT, 'qa_assistant'),
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


def submenu_perm_view_only(module_key: str, menu_key: str) -> bool:
    for item in get_module_submenus(module_key):
        if item['key'] == menu_key:
            return bool(item.get('perm_view_only'))
    return False


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
