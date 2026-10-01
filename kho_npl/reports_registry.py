REPORT_XNT = {
    'key': 'xnt',
    'title': 'Báo cáo xuất nhập tồn',
    'desc': 'Tồn đầu kỳ, nhập, xuất và tồn cuối kỳ theo từng mã hàng.',
    'view_name': 'kho_npl:report_hub',
    'export_name': 'kho_npl:report_export',
    'icon': 'bi-file-earmark-bar-graph',
}

REPORT_ISSUE_DETAIL = {
    'key': 'issue_detail',
    'title': 'Báo cáo chi tiết xuất',
    'desc': 'Chi tiết các dòng phiếu xuất, gom theo nhóm hàng, lọc theo ngày tạo phiếu.',
    'view_name': 'kho_npl:report_issue_detail',
    'export_name': 'kho_npl:report_issue_detail_export',
    'icon': 'bi-box-arrow-up',
}

REPORT_RECEIPT_DETAIL = {
    'key': 'receipt_detail',
    'title': 'Báo cáo chi tiết nhập',
    'desc': 'Chi tiết các dòng phiếu nhập, gom theo nhóm hàng, lọc theo ngày tạo phiếu.',
    'view_name': 'kho_npl:report_receipt_detail',
    'export_name': 'kho_npl:report_receipt_detail_export',
    'icon': 'bi-box-arrow-in-down',
}

REPORT_TABS = (REPORT_XNT, REPORT_ISSUE_DETAIL, REPORT_RECEIPT_DETAIL)
