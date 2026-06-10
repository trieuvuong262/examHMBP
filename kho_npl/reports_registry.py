REPORT_DEFINITIONS = {
    'ton-kho': {
        'title': 'Tồn kho hiện tại',
        'desc': 'Danh sách NPL theo mã, nhóm, tồn và trạng thái đủ/thiếu.',
        'icon': 'bi-boxes',
        'view_name': 'kho_npl:report_stock',
        'export_name': 'kho_npl:report_stock_export',
        'has_filters': False,
    },
    'bien-dong': {
        'title': 'Nhập — xuất — tồn',
        'desc': 'Biến động theo kỳ, theo từng nguyên phụ liệu.',
        'icon': 'bi-arrow-left-right',
        'view_name': 'kho_npl:report_movement',
        'export_name': 'kho_npl:report_movement_export',
        'has_filters': True,
    },
    'xuat-lsx': {
        'title': 'Xuất theo lệnh sản xuất',
        'desc': 'Tổng hợp xuất kho gắn LSX / mã sản phẩm.',
        'icon': 'bi-diagram-3',
        'view_name': 'kho_npl:report_issue_lsx',
        'export_name': 'kho_npl:report_issue_lsx_export',
        'has_filters': True,
    },
    'can-bao': {
        'title': 'NPL sắp thiếu / hết hàng',
        'desc': 'Cảnh báo dưới mức tồn tối thiểu.',
        'icon': 'bi-exclamation-triangle',
        'view_name': 'kho_npl:report_alerts',
        'export_name': 'kho_npl:report_alerts_export',
        'has_filters': False,
    },
    'kiem-ke': {
        'title': 'Lịch sử kiểm kê',
        'desc': 'Các kỳ kiểm kê và chênh lệch đã ghi nhận.',
        'icon': 'bi-journal-text',
        'view_name': 'kho_npl:report_stocktake_history',
        'export_name': 'kho_npl:report_stocktake_history_export',
        'has_filters': False,
    },
    'so-kho': {
        'title': 'Sổ kho chi tiết',
        'desc': 'Ledger từng biến động nhập, xuất, điều chỉnh.',
        'icon': 'bi-list-columns',
        'view_name': 'kho_npl:report_ledger',
        'export_name': 'kho_npl:report_ledger_export',
        'has_filters': True,
    },
}


def report_hub_items():
    return [
        {'slug': slug, **meta}
        for slug, meta in REPORT_DEFINITIONS.items()
    ]
