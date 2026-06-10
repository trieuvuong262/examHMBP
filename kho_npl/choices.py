"""Trạng thái và lựa chọn nghiệp vụ kho NPL."""

STOCK_STATUS_OK = 'ok'
STOCK_STATUS_LOW = 'low'
STOCK_STATUS_OUT = 'out'

STOCK_STATUS_LABELS = {
    STOCK_STATUS_OK: 'Đủ',
    STOCK_STATUS_LOW: 'Sắp thiếu',
    STOCK_STATUS_OUT: 'Hết hàng',
}

STOCK_STATUS_BADGE = {
    STOCK_STATUS_OK: 'success',
    STOCK_STATUS_LOW: 'warning',
    STOCK_STATUS_OUT: 'danger',
}

DOC_STATUS_DRAFT = 'draft'
DOC_STATUS_POSTED = 'posted'
DOC_STATUS_CANCELLED = 'cancelled'

DOC_STATUS_LABELS = {
    DOC_STATUS_DRAFT: 'Nháp',
    DOC_STATUS_POSTED: 'Đã ghi sổ',
    DOC_STATUS_CANCELLED: 'Đã hủy',
}

ISSUE_TYPE_PRODUCTION = 'production'
ISSUE_TYPE_SAMPLE = 'sample'
ISSUE_TYPE_WASTE = 'waste'
ISSUE_TYPE_RETURN = 'return_supplier'
ISSUE_TYPE_SCRAP = 'scrap'
ISSUE_TYPE_TRANSFER = 'transfer'

ISSUE_TYPE_CHOICES = [
    (ISSUE_TYPE_PRODUCTION, 'Xuất cho sản xuất'),
    (ISSUE_TYPE_SAMPLE, 'Xuất làm mẫu'),
    (ISSUE_TYPE_WASTE, 'Xuất bù hao hụt'),
    (ISSUE_TYPE_RETURN, 'Xuất trả nhà cung cấp'),
    (ISSUE_TYPE_SCRAP, 'Xuất hủy / hư hỏng'),
    (ISSUE_TYPE_TRANSFER, 'Xuất điều chuyển kho'),
]

ADJUST_STATUS_PENDING = 'pending'
ADJUST_STATUS_APPROVED = 'approved'
ADJUST_STATUS_REJECTED = 'rejected'

ADJUST_STATUS_LABELS = {
    ADJUST_STATUS_PENDING: 'Chờ duyệt',
    ADJUST_STATUS_APPROVED: 'Đã duyệt',
    ADJUST_STATUS_REJECTED: 'Từ chối',
}

STOCKTAKE_STATUS_DRAFT = 'draft'
STOCKTAKE_STATUS_COUNTING = 'counting'
STOCKTAKE_STATUS_REVIEW = 'review'
STOCKTAKE_STATUS_CLOSED = 'closed'

STOCKTAKE_STATUS_LABELS = {
    STOCKTAKE_STATUS_DRAFT: 'Nháp',
    STOCKTAKE_STATUS_COUNTING: 'Đang kiểm',
    STOCKTAKE_STATUS_REVIEW: 'Chờ duyệt',
    STOCKTAKE_STATUS_CLOSED: 'Đã chốt',
}

TRANSFER_STATUS_DRAFT = 'draft'
TRANSFER_STATUS_IN_TRANSIT = 'in_transit'
TRANSFER_STATUS_RECEIVED = 'received'
TRANSFER_STATUS_CANCELLED = 'cancelled'

TRANSFER_STATUS_LABELS = {
    TRANSFER_STATUS_DRAFT: 'Nháp',
    TRANSFER_STATUS_IN_TRANSIT: 'Đang chuyển',
    TRANSFER_STATUS_RECEIVED: 'Đã nhập',
    TRANSFER_STATUS_CANCELLED: 'Đã hủy',
}

TRANSFER_TAB_NHAP = 'nhap'
TRANSFER_TAB_CHUYEN = 'chuyen'
TRANSFER_TAB_NHAN = 'nhan'
TRANSFER_TAB_DANH_SACH = 'danh-sach'

TRANSFER_TAB_CHOICES = [
    (TRANSFER_TAB_NHAP, 'Nhập'),
    (TRANSFER_TAB_CHUYEN, 'Chuyển'),
    (TRANSFER_TAB_NHAN, 'Nhận'),
    (TRANSFER_TAB_DANH_SACH, 'Danh sách'),
]

TRANSFER_LIST_FILTER_ALL = ''
TRANSFER_LIST_FILTER_DRAFT = TRANSFER_STATUS_DRAFT
TRANSFER_LIST_FILTER_IN_TRANSIT = TRANSFER_STATUS_IN_TRANSIT
TRANSFER_LIST_FILTER_RECEIVED = TRANSFER_STATUS_RECEIVED

TRANSFER_LIST_STATUS_FILTERS = [
    (TRANSFER_LIST_FILTER_ALL, 'Tất cả'),
    (TRANSFER_LIST_FILTER_DRAFT, 'Đã nhập'),
    (TRANSFER_LIST_FILTER_IN_TRANSIT, 'Chưa nhận'),
    (TRANSFER_LIST_FILTER_RECEIVED, 'Đã nhận'),
]

TRANSFER_LIST_STATUS_DISPLAY = {
    TRANSFER_STATUS_DRAFT: 'Đã nhập',
    TRANSFER_STATUS_IN_TRANSIT: 'Chưa nhận',
    TRANSFER_STATUS_RECEIVED: 'Đã nhận',
    TRANSFER_STATUS_CANCELLED: 'Đã hủy',
}

WAREHOUSE_SCRAP_CODE = 'HUY'

DISPOSAL_REASON_DAMAGED = 'damaged'
DISPOSAL_REASON_DEFECTIVE = 'defective'
DISPOSAL_REASON_EXPIRED = 'expired'
DISPOSAL_REASON_OTHER = 'other'

DISPOSAL_REASON_CHOICES = [
    (DISPOSAL_REASON_DAMAGED, 'Hư hỏng'),
    (DISPOSAL_REASON_DEFECTIVE, 'Lỗi chất lượng'),
    (DISPOSAL_REASON_EXPIRED, 'Hết hạn / quá hạn'),
    (DISPOSAL_REASON_OTHER, 'Khác'),
]

DEFAULT_MATERIAL_CATEGORIES = [
    ('vai-chinh', 'Vải chính', 1),
    ('vai-phoi', 'Vải phối', 2),
    ('bo-co-tay', 'Bo cổ / bo tay', 3),
    ('day-khoa', 'Dây kéo / dây rút / nút / khoen', 4),
    ('tem-nhan', 'Tem nhãn / tag / size', 5),
    ('bao-bi', 'Bao bì / túi / thùng', 6),
    ('decal', 'Decal / vật tư in ép', 7),
    ('chi-may', 'Chỉ may', 8),
    ('khac', 'Phụ liệu khác', 9),
]
