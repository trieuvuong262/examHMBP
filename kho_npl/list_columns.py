"""Định nghĩa cột cho bảng danh sách Kho NPL (chọn cột + resize)."""


def _col(key, label, *, default=True, required=False):
    return {'key': key, 'label': label, 'default': default, 'required': required}


def columns_from_fields(field_labels, *, required_key=None):
    return [
        _col(key, label, required=(key == required_key))
        for key, label in field_labels
    ]


MATERIAL_LIST_COLUMNS = [
    _col('code', 'Mã', required=True),
    _col('name', 'Tên NPL'),
    _col('category', 'Nhóm'),
    _col('color', 'Màu'),
    _col('specification', 'Quy cách'),
    _col('unit', 'ĐVT'),
    _col('supplier', 'NCC'),
    _col('min_stock', 'Tối thiểu'),
    _col('status', 'Trạng thái'),
]

MATERIAL_STOCK_COLUMNS = [
    _col('code', 'Mã', required=True),
    _col('name', 'Tên NPL'),
    _col('color', 'Màu'),
    _col('unit', 'ĐVT'),
    _col('total_qty', 'Tồn'),
    _col('min_stock', 'Tối thiểu'),
    _col('primary_location', 'Vị trí'),
    _col('status', 'Trạng thái'),
]

STOCK_ALERT_COLUMNS = MATERIAL_STOCK_COLUMNS[:]
STOCK_ALERT_COLUMNS[4:6] = [_col('total_qty', 'Tồn'), _col('min_stock', 'Tối thiểu')]
STOCK_ALERT_COLUMNS.insert(3, _col('category', 'Nhóm'))
STOCK_ALERT_COLUMNS.insert(4, _col('specification', 'Quy cách'))

OVERVIEW_ALERT_COLUMNS = [
    _col('code', 'Mã', required=True),
    _col('name', 'Tên'),
    _col('category', 'Nhóm'),
    _col('total_qty', 'Tồn'),
    _col('min_stock', 'Tối thiểu'),
    _col('status', 'Trạng thái'),
]

RECEIPT_LIST_COLUMNS = [
    _col('number', 'Số phiếu', required=True),
    _col('date', 'Ngày nhập'),
    _col('supplier', 'NCC'),
    _col('po', 'PO'),
    _col('status', 'Trạng thái'),
    _col('creator', 'Người tạo'),
]

ISSUE_LIST_COLUMNS = [
    _col('number', 'Số phiếu', required=True),
    _col('date', 'Ngày xuất'),
    _col('type', 'Lý do'),
    _col('lsx', 'LSX / SP'),
    _col('status', 'Trạng thái'),
    _col('issuer', 'Người xuất'),
]

ADJUSTMENT_LIST_COLUMNS = [
    _col('number', 'Số phiếu', required=True),
    _col('date', 'Ngày'),
    _col('material', 'NPL'),
    _col('location', 'Vị trí'),
    _col('system_qty', 'Hệ thống'),
    _col('actual_qty', 'Thực tế'),
    _col('variance', 'Chênh'),
    _col('status', 'Trạng thái'),
]

DISPOSAL_LIST_COLUMNS = [
    _col('number', 'Số phiếu', required=True),
    _col('date', 'Ngày hủy'),
    _col('location', 'Kho nguồn'),
    _col('reason', 'Lý do'),
    _col('status', 'Trạng thái'),
    _col('creator', 'Người tạo'),
]

STOCKTAKE_LIST_COLUMNS = [
    _col('number', 'Mã kỳ', required=True),
    _col('name', 'Tên'),
    _col('date', 'Ngày'),
    _col('status', 'Trạng thái'),
    _col('creator', 'Người tạo'),
]

TRANSFER_LIST_COLUMNS = [
    _col('number', 'Số phiếu', required=True),
    _col('date', 'Ngày'),
    _col('from_loc', 'Kho gửi'),
    _col('arrow', '→', default=False),
    _col('to_loc', 'Kho nhận'),
    _col('list_status', 'Trạng thái', default=False),
    _col('creator', 'Người tạo'),
]

STOCK_CARD_CATALOG_COLUMNS = [
    _col('stt', 'STT', default=False),
    _col('code', 'Mã', required=True),
    _col('name', 'Tên NPL'),
    _col('category', 'Nhóm'),
    _col('specification', 'Quy cách'),
    _col('stock_total', 'Tồn'),
]

STOCK_CARD_LEDGER_COLUMNS = [
    _col('idx', '#', default=False),
    _col('date', 'Ngày', required=True),
    _col('ref', 'Phiếu'),
    _col('type', 'Loại'),
    _col('location', 'Vị trí'),
    _col('balance_before', 'Tồn đầu'),
    _col('qty_in', 'SL nhập'),
    _col('qty_out', 'SL xuất'),
    _col('qty_delta', 'Biến động'),
    _col('balance_after', 'Tồn sau'),
    _col('notes', 'Ghi chú', default=False),
]

RECEIPT_LINE_COLUMNS = [
    _col('material_code', 'Mã NPL', required=True),
    _col('material_name', 'Tên'),
    _col('ordered_qty', 'SL đặt'),
    _col('received_qty', 'SL nhập'),
    _col('location', 'Vị trí'),
    _col('notes', 'Ghi chú', default=False),
]

ISSUE_LINE_COLUMNS = [
    _col('material_code', 'Mã NPL', required=True),
    _col('material_name', 'Tên'),
    _col('quantity', 'Số lượng'),
    _col('location', 'Vị trí'),
    _col('notes', 'Ghi chú', default=False),
]

TRANSFER_LINE_COLUMNS = [
    _col('material_code', 'Mã NPL', required=True),
    _col('material_name', 'Tên'),
    _col('quantity', 'Số lượng'),
    _col('notes', 'Ghi chú', default=False),
]

DISPOSAL_LINE_COLUMNS = ISSUE_LINE_COLUMNS[:]

STOCKTAKE_LINE_COLUMNS = [
    _col('material_code', 'NPL', required=True),
    _col('location', 'Vị trí'),
    _col('system_qty', 'HT'),
    _col('actual_qty', 'TT'),
    _col('variance', 'Chênh'),
]

MATERIAL_BALANCE_COLUMNS = [
    _col('location', 'Vị trí', required=True),
    _col('quantity', 'Số lượng'),
]

# Giữ tương thích import cũ
MATERIAL_LIST_COLUMN_KEYS = {c['key'] for c in MATERIAL_LIST_COLUMNS}
MATERIAL_LIST_DEFAULT_VISIBLE = {c['key'] for c in MATERIAL_LIST_COLUMNS if c['default']}
MATERIAL_LIST_REQUIRED_KEYS = {c['key'] for c in MATERIAL_LIST_COLUMNS if c.get('required')}


STOCKTAKE_COUNT_COLUMNS = [
    _col('material_code', 'NPL', required=True),
    _col('location', 'Vị trí'),
    _col('system_qty', 'Tồn HT'),
    _col('actual_qty', 'Tồn TT'),
    _col('notes', 'Ghi chú', default=False),
]


def report_column_defs(column_labels):
    """Báo cáo động — key trùng nhãn cột trong dict dòng."""
    return [
        _col(label, label, required=(i == 0))
        for i, label in enumerate(column_labels or [])
    ]
