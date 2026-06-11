"""Cột và sắp xếp bảng danh sách phiếu kho NPL."""

RECEIPT_LIST_COLUMNS = [
    {'key': 'number', 'label': 'Số phiếu', 'default': True, 'required': True, 'weight': 100},
    {'key': 'receipt_date', 'label': 'Ngày nhập', 'default': True, 'required': False, 'weight': 100},
    {'key': 'supplier', 'label': 'NCC', 'default': True, 'required': False, 'weight': 150},
    {'key': 'po_number', 'label': 'PO', 'default': True, 'required': False, 'weight': 100},
    {'key': 'status', 'label': 'Trạng thái', 'default': True, 'required': False, 'weight': 100},
    {'key': 'created_by', 'label': 'Người tạo', 'default': True, 'required': False, 'weight': 120},
]
RECEIPT_LIST_TOTAL_COL_WEIGHT = sum(c['weight'] for c in RECEIPT_LIST_COLUMNS)
RECEIPT_LIST_SORT_FIELDS = {
    'number': 'number',
    'receipt_date': 'receipt_date',
    'supplier': 'supplier__name',
    'po_number': 'po_number',
    'status': 'status',
    'created_by': 'created_by__username',
}

ISSUE_LIST_COLUMNS = [
    {'key': 'number', 'label': 'Số phiếu', 'default': True, 'required': True, 'weight': 100},
    {'key': 'issue_date', 'label': 'Ngày xuất', 'default': True, 'required': False, 'weight': 100},
    {'key': 'issue_type', 'label': 'Lý do', 'default': True, 'required': False, 'weight': 120},
    {'key': 'production_ref', 'label': 'LSX / SP', 'default': True, 'required': False, 'weight': 130},
    {'key': 'status', 'label': 'Trạng thái', 'default': True, 'required': False, 'weight': 100},
    {'key': 'issued_by', 'label': 'Người xuất', 'default': True, 'required': False, 'weight': 120},
]
ISSUE_LIST_TOTAL_COL_WEIGHT = sum(c['weight'] for c in ISSUE_LIST_COLUMNS)
ISSUE_LIST_SORT_FIELDS = {
    'number': 'number',
    'issue_date': 'issue_date',
    'issue_type': 'issue_type',
    'production_ref': 'production_order',
    'status': 'status',
    'issued_by': 'issued_by__username',
}

DISPOSAL_LIST_COLUMNS = [
    {'key': 'number', 'label': 'Số phiếu', 'default': True, 'required': True, 'weight': 100},
    {'key': 'disposal_date', 'label': 'Ngày hủy', 'default': True, 'required': False, 'weight': 100},
    {'key': 'from_location', 'label': 'Kho nguồn', 'default': True, 'required': False, 'weight': 100},
    {'key': 'reason', 'label': 'Lý do', 'default': True, 'required': False, 'weight': 120},
    {'key': 'status', 'label': 'Trạng thái', 'default': True, 'required': False, 'weight': 100},
    {'key': 'created_by', 'label': 'Người tạo', 'default': True, 'required': False, 'weight': 120},
]
DISPOSAL_LIST_TOTAL_COL_WEIGHT = sum(c['weight'] for c in DISPOSAL_LIST_COLUMNS)
DISPOSAL_LIST_SORT_FIELDS = {
    'number': 'number',
    'disposal_date': 'disposal_date',
    'from_location': 'from_location__code',
    'reason': 'reason',
    'status': 'status',
    'created_by': 'created_by__username',
}

STOCKTAKE_LIST_COLUMNS = [
    {'key': 'number', 'label': 'Mã kỳ', 'default': True, 'required': True, 'weight': 100},
    {'key': 'name', 'label': 'Tên', 'default': True, 'required': False, 'weight': 140},
    {'key': 'location', 'label': 'Kho', 'default': True, 'required': False, 'weight': 90},
    {'key': 'stocktake_date', 'label': 'Ngày', 'default': True, 'required': False, 'weight': 90},
    {'key': 'status', 'label': 'Trạng thái', 'default': True, 'required': False, 'weight': 100},
    {'key': 'created_by', 'label': 'Người tạo', 'default': True, 'required': False, 'weight': 110},
]
STOCKTAKE_LIST_TOTAL_COL_WEIGHT = sum(c['weight'] for c in STOCKTAKE_LIST_COLUMNS)
STOCKTAKE_LIST_SORT_FIELDS = {
    'number': 'number',
    'name': 'name',
    'location': 'location__code',
    'stocktake_date': 'stocktake_date',
    'status': 'status',
    'created_by': 'created_by__username',
}

TRANSFER_LIST_COLUMNS = [
    {'key': 'number', 'label': 'Số phiếu', 'default': True, 'required': True, 'weight': 100},
    {'key': 'transfer_date', 'label': 'Ngày', 'default': True, 'required': False, 'weight': 100},
    {'key': 'from_location', 'label': 'Kho gửi', 'default': True, 'required': False, 'weight': 100},
    {'key': 'to_location', 'label': 'Kho nhận', 'default': True, 'required': False, 'weight': 100},
    {'key': 'created_by', 'label': 'Người tạo', 'default': True, 'required': False, 'weight': 120},
]
TRANSFER_LIST_COLUMNS_WITH_STATUS = [
    *TRANSFER_LIST_COLUMNS[:4],
    {'key': 'status', 'label': 'Trạng thái', 'default': True, 'required': False, 'weight': 100},
    *TRANSFER_LIST_COLUMNS[4:],
]
TRANSFER_LIST_TOTAL_COL_WEIGHT = sum(c['weight'] for c in TRANSFER_LIST_COLUMNS)
TRANSFER_LIST_TOTAL_COL_WEIGHT_WITH_STATUS = sum(c['weight'] for c in TRANSFER_LIST_COLUMNS_WITH_STATUS)
TRANSFER_LIST_SORT_FIELDS = {
    'number': 'number',
    'transfer_date': 'transfer_date',
    'from_location': 'from_location__code',
    'to_location': 'to_location__code',
    'status': 'status',
    'created_by': 'created_by__username',
}
