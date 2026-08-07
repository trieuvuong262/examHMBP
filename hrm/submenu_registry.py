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
    MODULE_SURVEYS,
    MODULE_HO_TRO,
    MODULE_KHO_NPL,
    MODULE_KHO_SAN_PHAM,
    MODULE_KIOTVIET,
    MODULE_SAN_XUAT,
    MODULE_NAS_STORAGE,
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
        {
            'key': 'report_stats',
            'label': 'Thống kê báo cáo',
            'icon': 'bi-table',
            'perm_view_only': True,
        },
        {'key': 'general_settings', 'label': 'Thiết lập chung', 'icon': 'bi-gear'},
        {'key': 'daily_vp', 'label': 'Báo cáo VP', 'icon': 'bi-clipboard-check'},
        {'key': 'daily_vp_detail', 'label': 'Quản lý BC (VP)', 'icon': 'bi-people-fill'},
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
    MODULE_SURVEYS: [
        {'key': 'create', 'label': 'Đặt câu hỏi', 'icon': 'bi-plus-circle'},
        {'key': 'share', 'label': 'Tạo link gửi NV', 'icon': 'bi-send'},
        {'key': 'results', 'label': 'Kết quả', 'icon': 'bi-inbox-fill'},
    ],
    MODULE_UTILITIES: [
        {'key': 'meal_ordering', 'label': 'Đặt cơm', 'icon': 'bi-cup-hot'},
        {'key': 'salary_advance', 'label': 'Ứng lương', 'icon': 'bi-cash-coin'},
        {'key': 'schedule_reminder', 'label': 'Nhắc lịch', 'icon': 'bi-alarm'},
    ],
    MODULE_KHO_NPL: [
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
    MODULE_KHO_SAN_PHAM: [
        {'key': 'products', 'label': 'Danh mục', 'icon': 'bi-tags'},
        {'key': 'code_settings', 'label': 'Thiết lập mã', 'icon': 'bi-upc'},
    ],
    MODULE_SAN_XUAT: [
        {'key': 'overview', 'label': 'Tổng quan', 'icon': 'bi-speedometer2'},
        {'key': 'orders', 'label': 'Danh sách đơn đặt hàng', 'icon': 'bi-cart-check'},
        {'key': 'order_create', 'label': 'Lên đơn đặt hàng', 'icon': 'bi-cart-plus'},
        {'key': 'order_confirm', 'label': 'Xác nhận đơn đặt hàng', 'icon': 'bi-check2-square'},
        {'key': 'products_nvl', 'label': 'Sản phẩm – NVL', 'icon': 'bi-box'},
        {'key': 'docs', 'label': 'Hồ sơ thiết kế', 'icon': 'bi-journal-text'},
        {'key': 'bom', 'label': 'BOM', 'icon': 'bi-diagram-3'},
        {'key': 'capacity', 'label': 'Năng lực SX', 'icon': 'bi-speedometer'},
        {'key': 'capacity_load', 'label': 'Tải năng lực theo tổ', 'icon': 'bi-bar-chart-steps'},
        {'key': 'plan', 'label': 'Kế hoạch sản xuất', 'icon': 'bi-calendar3'},
        {'key': 'plan_board', 'label': 'Kế hoạch sản xuất (theo đơn)', 'icon': 'bi-kanban'},
        {'key': 'plan_progress', 'label': 'Giám sát tiến độ (đã gộp)', 'icon': 'bi-clipboard-data'},
        {'key': 'plan_overall', 'label': 'KH tổng thể (đã gộp)', 'icon': 'bi-calendar-range'},
        {'key': 'plan_detail', 'label': 'KH chi tiết (đã gộp)', 'icon': 'bi-list-columns'},
        {'key': 'stock_policy', 'label': 'Chính sách tồn thành phẩm', 'icon': 'bi-sliders'},
        {'key': 'restock', 'label': 'Đề xuất sản xuất bù tồn', 'icon': 'bi-lightbulb'},
        {'key': 'plan_npl', 'label': 'Kế hoạch nguyên phụ liệu', 'icon': 'bi-boxes'},
        {'key': 'npl_pr', 'label': 'Yêu cầu mua nguyên phụ liệu', 'icon': 'bi-cart-plus'},
        {'key': 'purchase_order', 'label': 'Đơn mua hàng', 'icon': 'bi-receipt'},
        {'key': 'plan_audit', 'label': 'Nhật ký kế hoạch', 'icon': 'bi-journal-check'},
        {'key': 'npl_stock', 'label': 'Kho Nguyên Phụ Liệu', 'icon': 'bi-boxes'},
        {'key': 'dispatch', 'label': 'Điều phối', 'icon': 'bi-diagram-2'},
        {'key': 'mo', 'label': 'Lệnh sản xuất', 'icon': 'bi-file-earmark-gear'},
        {'key': 'schedule', 'label': 'Lịch sản xuất', 'icon': 'bi-calendar-week'},
        {'key': 'material_issue_req', 'label': 'Yêu cầu xuất vật tư', 'icon': 'bi-box-arrow-right'},
        {'key': 'prod_stats', 'label': 'Thống kê sản xuất', 'icon': 'bi-bar-chart'},
        {'key': 'wip_handover', 'label': 'Bàn giao bán thành phẩm', 'icon': 'bi-arrow-left-right'},
        {'key': 'wip_return', 'label': 'Trả lại bán thành phẩm', 'icon': 'bi-arrow-return-left'},
        {'key': 'handover_status', 'label': 'Tình hình bàn giao SX', 'icon': 'bi-clipboard-data'},
        {'key': 'fg_receipt_req', 'label': 'Yêu cầu nhập thành phẩm', 'icon': 'bi-box-arrow-in-down'},
        {'key': 'disassembly', 'label': 'Lệnh tháo dỡ', 'icon': 'bi-box-arrow-up'},
        {'key': 'npl_surplus', 'label': 'NPL thừa', 'icon': 'bi-recycle'},
        {'key': 'shop_floor', 'label': 'Xác nhận xưởng', 'icon': 'bi-phone'},
        {'key': 'work_assign', 'label': 'Giao việc SX', 'icon': 'bi-person-workspace'},
        {'key': 'downtime', 'label': 'Dừng chuyền / OEE', 'icon': 'bi-pause-circle'},
        {'key': 'piece_rate', 'label': 'Lương sản phẩm', 'icon': 'bi-cash-coin'},
        {'key': 'qc', 'label': 'Kiểm tra chất lượng', 'icon': 'bi-clipboard-check'},
        {'key': 'qc_request', 'label': 'Yêu cầu kiểm tra', 'icon': 'bi-clipboard-plus'},
        {'key': 'qc_sheet', 'label': 'Phiếu kiểm tra', 'icon': 'bi-clipboard-check'},
        {'key': 'ncr', 'label': 'NCR', 'icon': 'bi-exclamation-octagon'},
        {'key': 'qc_criteria', 'label': 'Tiêu chí chất lượng', 'icon': 'bi-list-check'},
        {'key': 'qc_criteria_group', 'label': 'Nhóm tiêu chí chất lượng', 'icon': 'bi-collection'},
        {'key': 'qc_sampling', 'label': 'Phương pháp chọn mẫu', 'icon': 'bi-pie-chart'},
        {'key': 'qc_standard_set', 'label': 'Bộ tiêu chuẩn kiểm tra chất lượng', 'icon': 'bi-journal-bookmark'},
        {'key': 'qc_defect', 'label': 'Lỗi kiểm tra chất lượng', 'icon': 'bi-exclamation-triangle'},
        {'key': 'qc_defect_group', 'label': 'Nhóm lỗi kiểm tra chất lượng', 'icon': 'bi-folder-x'},
        {'key': 'packing', 'label': 'Đóng gói', 'icon': 'bi-box2'},
        {'key': 'subcontract', 'label': 'Thuê gia công', 'icon': 'bi-building'},
        {'key': 'costing_hub', 'label': 'Giá thành kế hoạch', 'icon': 'bi-cash-stack'},
        {'key': 'costing_norm', 'label': 'Giá thành định mức sản phẩm', 'icon': 'bi-calculator'},
        {'key': 'costing_so', 'label': 'Giá thành kế hoạch theo đơn đặt hàng', 'icon': 'bi-cart-check'},
        {'key': 'costing', 'label': 'Costing', 'icon': 'bi-calculator'},
        {'key': 'actual_cost', 'label': 'Giá thành thực tế', 'icon': 'bi-cash'},
        {'key': 'fg_stock', 'label': 'Kho sản phẩm', 'icon': 'bi-box-seam'},
        {'key': 'fg_products', 'label': 'Hàng hoá', 'icon': 'bi-box-seam'},
        {'key': 'fg_stock_list', 'label': 'Tồn kho thành phẩm', 'icon': 'bi-boxes'},
        {'key': 'fg_purchases', 'label': 'Phiếu nhập', 'icon': 'bi-box-arrow-in-down'},
        {'key': 'traceability', 'label': 'Truy xuất nguồn gốc', 'icon': 'bi-search'},
        {'key': 'ops_report', 'label': 'Báo cáo vận hành', 'icon': 'bi-graph-up'},
        {'key': 'process', 'label': 'Quy trình', 'icon': 'bi-signpost-2'},
        {'key': 'unified_catalog', 'label': 'Catalog thống nhất', 'icon': 'bi-collection'},
        {'key': 'staging', 'label': 'Vị trí staging', 'icon': 'bi-geo'},
        {'key': 'general_settings', 'label': 'Thiết lập chung', 'icon': 'bi-gear'},
    ],
    MODULE_KIOTVIET: [
        {'key': 'customers', 'label': 'Tra cứu khách hàng', 'icon': 'bi-person-vcard'},
        {'key': 'orders', 'label': 'Đơn đặt hàng', 'icon': 'bi-cart-check'},
        {'key': 'invoices', 'label': 'Hóa đơn', 'icon': 'bi-receipt'},
        {'key': 'products', 'label': 'Hàng hoá', 'icon': 'bi-box-seam'},
        {'key': 'stock', 'label': 'Tồn kho', 'icon': 'bi-boxes'},
        {'key': 'purchases', 'label': 'Phiếu nhập', 'icon': 'bi-box-arrow-in-down'},
    ],
    MODULE_NAS_STORAGE: [
        {'key': 'browse', 'label': 'Duyệt thư mục', 'icon': 'bi-folder2-open'},
        {
            'key': 'permissions',
            'label': 'Phân quyền thư mục NAS',
            'icon': 'bi-shield-lock',
            'perm_manage': True,
        },
    ],
    MODULE_DOCUMENTS: [
        {'key': 'browse', 'label': 'Tài liệu', 'icon': 'bi-folder2-open'},
        {'key': 'qa', 'label': 'Hỏi đáp', 'icon': 'bi-chat-dots-fill'},
        {
            'key': 'nas_download',
            'label': 'Tải bộ cài',
            'icon': 'bi-download',
            'perm_view_only': True,
        },
        {'key': 'rustdesk_config', 'label': 'Cấu hình RustDesk', 'perm_label': 'Cấu hình RustDesk', 'icon': 'bi-pc-display-horizontal', 'perm_manage': True},
        {'key': 'equipment_scan', 'label': 'Quét thiết bị', 'perm_label': 'Quét thiết bị IT', 'icon': 'bi-cpu', 'perm_manage': True},
    ],
    MODULE_AUDIT: [
        {'key': 'login_security', 'label': 'Bảo mật đăng nhập', 'icon': 'bi-shield-lock'},
        {'key': 'logs', 'label': 'Nhật ký thao tác', 'icon': 'bi-journal-check'},
        {'key': 'rustdesk', 'label': 'RustDesk', 'perm_label': 'Quản lý RustDesk', 'icon': 'bi-display', 'perm_manage': True},
        {'key': 'backup', 'label': 'Backup lên NAS', 'icon': 'bi-cloud-arrow-up'},
        {'key': 'vps_monitor', 'label': 'Giám sát VPS', 'perm_label': 'Giám sát VPS', 'icon': 'bi-speedometer2', 'perm_manage': True},
        {'key': 'nas_monitor', 'label': 'Giám sát NAS', 'perm_label': 'Giám sát NAS', 'icon': 'bi-hdd-network', 'perm_manage': True},
        {'key': 'kiotviet_sync', 'label': 'Đồng bộ KiotViet', 'icon': 'bi-arrow-repeat'},
        {'key': 'nas_links', 'label': 'Cập nhật link NAS', 'icon': 'bi-hdd-network'},
        {'key': 'zalo_oa', 'label': 'Zalo OA', 'perm_label': 'Cấu hình Zalo OA', 'icon': 'bi-chat-dots', 'perm_manage': True},
        {'key': 'email_config', 'label': 'Email', 'perm_label': 'Cấu hình Email', 'icon': 'bi-envelope', 'perm_manage': True},
        {'key': 'push_config', 'label': 'Thông báo đẩy', 'perm_label': 'Quản lý thông báo đẩy', 'icon': 'bi-bell', 'perm_manage': True},
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
    ('/reports/sx/thong-ke', MODULE_REPORTS, 'report_stats'),
    ('/reports/sx/thiet-lap', MODULE_REPORTS, 'general_settings'),
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
    ('/tien-ich/nhac-lich', MODULE_UTILITIES, 'schedule_reminder'),
    ('/cong-cu/nhac-lich', MODULE_UTILITIES, 'schedule_reminder'),
    # Góp ý
    ('/gop-y/danh-sach', MODULE_FEEDBACK, 'list'),
    ('/gop-y/tao', MODULE_FEEDBACK, 'create'),
    ('/khao-sat/quan-ly/tao', MODULE_SURVEYS, 'create'),
    ('/link-gui', MODULE_SURVEYS, 'share'),
    ('/khao-sat/quan-ly/', MODULE_SURVEYS, 'share'),
    ('/khao-sat/ket-qua', MODULE_SURVEYS, 'results'),
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
    ('/kho-npl/canh-bao', MODULE_KHO_NPL, 'material_stock'),
    ('/kho-npl/tong-quan', MODULE_KHO_NPL, 'material_stock'),
    ('/kho-san-pham/thiet-lap-ma', MODULE_KHO_SAN_PHAM, 'code_settings'),
    ('/kho-san-pham/danh-muc', MODULE_KHO_SAN_PHAM, 'products'),
    ('/kho-san-pham/', MODULE_KHO_SAN_PHAM, 'products'),
    # Sản xuất hub — prefix cụ thể trước; /san-xuat/ cuối cùng → overview
    ('/san-xuat/tong-quan', MODULE_SAN_XUAT, 'overview'),
    ('/san-xuat/don-hang/them', MODULE_SAN_XUAT, 'order_create'),
    ('/san-xuat/don-hang/xac-nhan', MODULE_SAN_XUAT, 'order_confirm'),
    ('/san-xuat/don-hang', MODULE_SAN_XUAT, 'orders'),
    ('/san-xuat/san-pham-nvl', MODULE_SAN_XUAT, 'products_nvl'),
    ('/san-xuat/ke-hoach/bang', MODULE_SAN_XUAT, 'plan_board'),
    ('/san-xuat/ke-hoach/giam-sat-tien-do', MODULE_SAN_XUAT, 'plan_progress'),
    ('/san-xuat/ke-hoach/tong-the', MODULE_SAN_XUAT, 'plan_overall'),
    ('/san-xuat/ke-hoach/chi-tiet', MODULE_SAN_XUAT, 'plan_detail'),
    ('/san-xuat/nang-luc/tai-theo-to', MODULE_SAN_XUAT, 'capacity_load'),
    ('/san-xuat/ke-hoach/chinh-sach-ton', MODULE_SAN_XUAT, 'stock_policy'),
    ('/san-xuat/ke-hoach/de-xuat-bu-ton', MODULE_SAN_XUAT, 'restock'),
    ('/san-xuat/ke-hoach/npl', MODULE_SAN_XUAT, 'plan_npl'),
    ('/san-xuat/ke-hoach/yeu-cau-mua-npl', MODULE_SAN_XUAT, 'npl_pr'),
    ('/san-xuat/ke-hoach/don-mua-hang', MODULE_SAN_XUAT, 'purchase_order'),
    ('/san-xuat/ke-hoach/nhat-ky', MODULE_SAN_XUAT, 'plan_audit'),
    ('/san-xuat/ke-hoach', MODULE_SAN_XUAT, 'plan_board'),
    ('/san-xuat/dieu-phoi/chay-lenh-moi', MODULE_SAN_XUAT, 'mo'),
    ('/san-xuat/dieu-phoi/lenh-sx', MODULE_SAN_XUAT, 'mo'),
    ('/san-xuat/dieu-phoi/lenh-thao-do', MODULE_SAN_XUAT, 'disassembly'),
    ('/san-xuat/dieu-phoi/lich-sx', MODULE_SAN_XUAT, 'schedule'),
    ('/san-xuat/dieu-phoi/yeu-cau-xuat-vt', MODULE_SAN_XUAT, 'material_issue_req'),
    ('/san-xuat/dieu-phoi/thong-ke-sx', MODULE_SAN_XUAT, 'prod_stats'),
    ('/san-xuat/dieu-phoi/yeu-cau-nhap-tp', MODULE_SAN_XUAT, 'fg_receipt_req'),
    ('/san-xuat/dieu-phoi/npl-thua', MODULE_SAN_XUAT, 'npl_surplus'),
    ('/san-xuat/dieu-phoi/ban-giao-btp', MODULE_SAN_XUAT, 'wip_handover'),
    ('/san-xuat/dieu-phoi/tra-lai-btp', MODULE_SAN_XUAT, 'wip_return'),
    ('/san-xuat/dieu-phoi/tinh-hinh-ban-giao', MODULE_SAN_XUAT, 'handover_status'),
    ('/san-xuat/dieu-phoi', MODULE_SAN_XUAT, 'dispatch'),
    ('/san-xuat/chat-luong/yeu-cau', MODULE_SAN_XUAT, 'qc_request'),
    ('/san-xuat/chat-luong/phieu', MODULE_SAN_XUAT, 'qc_sheet'),
    ('/san-xuat/chat-luong/canh-bao', MODULE_SAN_XUAT, 'qc'),
    ('/san-xuat/chat-luong/tieu-chi', MODULE_SAN_XUAT, 'qc_criteria'),
    ('/san-xuat/chat-luong/nhom-tieu-chi', MODULE_SAN_XUAT, 'qc_criteria_group'),
    ('/san-xuat/chat-luong/chon-mau', MODULE_SAN_XUAT, 'qc_sampling'),
    ('/san-xuat/chat-luong/bo-tieu-chuan', MODULE_SAN_XUAT, 'qc_standard_set'),
    ('/san-xuat/chat-luong/loi', MODULE_SAN_XUAT, 'qc_defect'),
    ('/san-xuat/chat-luong/nhom-loi', MODULE_SAN_XUAT, 'qc_defect_group'),
    ('/san-xuat/chat-luong', MODULE_SAN_XUAT, 'qc'),
    ('/san-xuat/gia-thanh/thuc-te', MODULE_SAN_XUAT, 'actual_cost'),
    ('/san-xuat/gia-thanh/dinh-muc', MODULE_SAN_XUAT, 'costing_norm'),
    ('/san-xuat/gia-thanh/theo-don', MODULE_SAN_XUAT, 'costing_so'),
    ('/san-xuat/gia-thanh/loai-chi-phi', MODULE_SAN_XUAT, 'costing_hub'),
    ('/san-xuat/gia-thanh', MODULE_SAN_XUAT, 'costing_hub'),
    ('/san-xuat/kho-san-pham/hang-hoa', MODULE_SAN_XUAT, 'fg_products'),
    ('/san-xuat/kho-san-pham/ton-kho', MODULE_SAN_XUAT, 'fg_stock_list'),
    ('/san-xuat/kho-san-pham/phieu-nhap', MODULE_SAN_XUAT, 'fg_purchases'),
    ('/san-xuat/kho-san-pham', MODULE_SAN_XUAT, 'fg_stock'),
    ('/san-xuat/kho-npl', MODULE_SAN_XUAT, 'npl_stock'),
    ('/san-xuat/thiet-lap', MODULE_SAN_XUAT, 'general_settings'),
    ('/san-xuat/quy-trinh', MODULE_SAN_XUAT, 'process'),
    ('/san-xuat/ho-so', MODULE_SAN_XUAT, 'docs'),
    ('/san-xuat/bom', MODULE_SAN_XUAT, 'bom'),
    ('/san-xuat/nang-luc', MODULE_SAN_XUAT, 'capacity'),
    ('/san-xuat/shop-floor', MODULE_SAN_XUAT, 'shop_floor'),
    ('/san-xuat/giao-viec', MODULE_SAN_XUAT, 'work_assign'),
    ('/san-xuat/dung-chuyen', MODULE_SAN_XUAT, 'downtime'),
    ('/san-xuat/luong-san-pham', MODULE_SAN_XUAT, 'piece_rate'),
    ('/san-xuat/ncr', MODULE_SAN_XUAT, 'ncr'),
    ('/san-xuat/dong-goi', MODULE_SAN_XUAT, 'packing'),
    ('/san-xuat/thue-gia-cong', MODULE_SAN_XUAT, 'subcontract'),
    ('/san-xuat/truy-xuat', MODULE_SAN_XUAT, 'traceability'),
    ('/san-xuat/bao-cao-van-hanh', MODULE_SAN_XUAT, 'ops_report'),
    ('/san-xuat/catalog', MODULE_SAN_XUAT, 'unified_catalog'),
    ('/san-xuat/staging', MODULE_SAN_XUAT, 'staging'),
    ('/san-xuat/api/', MODULE_SAN_XUAT, 'overview'),
    ('/san-xuat/', MODULE_SAN_XUAT, 'overview'),
    # KiotViet
    ('/kiotviet/phieu-nhap', MODULE_KIOTVIET, 'purchases'),
    ('/kiotviet/ton-kho', MODULE_KIOTVIET, 'stock'),
    ('/kiotviet/hang-hoa', MODULE_KIOTVIET, 'products'),
    ('/kiotviet/hoa-don', MODULE_KIOTVIET, 'invoices'),
    ('/kiotviet/don-dat-hang', MODULE_KIOTVIET, 'orders'),
    ('/kiotviet/khach-hang', MODULE_KIOTVIET, 'customers'),
    # NAS
    ('/thu-muc-nas/phan-quyen', MODULE_NAS_STORAGE, 'permissions'),
    ('/thu-muc-nas/cai-dat', MODULE_DOCUMENTS, 'nas_download'),
    ('/thu-muc-nas/', MODULE_NAS_STORAGE, 'browse'),
    # Tài liệu
    ('/tai-lieu/quet-thiet-bi', MODULE_DOCUMENTS, 'equipment_scan'),
    ('/tai-lieu/cau-hinh-rustdesk', MODULE_DOCUMENTS, 'rustdesk_config'),
    ('/tai-lieu/tai-nas', MODULE_DOCUMENTS, 'nas_download'),
    ('/tai-lieu/hoi-dap', MODULE_DOCUMENTS, 'qa'),
    ('/tai-lieu/admin', MODULE_DOCUMENTS, 'browse'),
    ('/tai-lieu/file', MODULE_DOCUMENTS, 'browse'),
    ('/tai-lieu/', MODULE_DOCUMENTS, 'browse'),
    # Quản trị hệ thống
    ('/nhat-ky/thong-bao-day', MODULE_AUDIT, 'push_config'),
    ('/nhat-ky/email', MODULE_AUDIT, 'email_config'),
    ('/nhat-ky/zalo-oa', MODULE_AUDIT, 'zalo_oa'),
    ('/nhat-ky/tro-ly-ai', MODULE_AUDIT, 'qa_assistant'),
    ('/nhat-ky/bao-mat-dang-nhap', MODULE_AUDIT, 'login_security'),
    ('/nhat-ky/rustdesk/trang-thai', MODULE_AUDIT, 'rustdesk'),
    ('/nhat-ky/rustdesk/tai-cai-dat', MODULE_AUDIT, 'rustdesk'),
    ('/nhat-ky/rustdesk/tai-cau-hinh-it', MODULE_AUDIT, 'rustdesk'),
    ('/nhat-ky/rustdesk/them', MODULE_AUDIT, 'rustdesk'),
    ('/nhat-ky/rustdesk/', MODULE_AUDIT, 'rustdesk'),
    ('/nhat-ky/backup', MODULE_AUDIT, 'backup'),
    ('/nhat-ky/vps', MODULE_AUDIT, 'vps_monitor'),
    ('/nhat-ky/nas', MODULE_AUDIT, 'nas_monitor'),
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
            return item.get('perm_label') or item['label']
    return menu_key


def submenu_perm_view_only(module_key: str, menu_key: str) -> bool:
    for item in get_module_submenus(module_key):
        if item['key'] == menu_key:
            return bool(item.get('perm_view_only'))
    return False


def submenu_perm_manage(module_key: str, menu_key: str) -> bool:
    """Menu con trong module chỉ xem/xuất — vẫn cho phép đủ 5 quyền (vd. RustDesk)."""
    for item in get_module_submenus(module_key):
        if item['key'] == menu_key:
            return bool(item.get('perm_manage'))
    return False


def perm_field_name(action: str, module_key: str, menu_key: str | None = None) -> str:
    if menu_key:
        return f'{action}_{module_key}{MENU_FIELD_SEP}{menu_key}'
    return f'{action}_{module_key}'


def parse_perm_field_name(field_name: str) -> tuple[str, str, str | None]:
    """Trả về (action, module_key, menu_key|None)."""
    from hrm.group_permissions import PERM_ACTIONS

    for action in PERM_ACTIONS:
        prefix = f'{action}_'
        if not field_name.startswith(prefix):
            continue
        rest = field_name[len(prefix):]
        if MENU_FIELD_SEP in rest:
            module_key, menu_key = rest.split(MENU_FIELD_SEP, 1)
            return action, module_key, menu_key
        return action, rest, None
    raise ValueError(f'Invalid permission field: {field_name}')
