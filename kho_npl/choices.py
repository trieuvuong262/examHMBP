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

RECEIPT_STATUS_LABELS = {
    **DOC_STATUS_LABELS,
    DOC_STATUS_DRAFT: 'Đã tạo',
    DOC_STATUS_POSTED: 'Đã nhập kho',
}

ISSUE_STATUS_LABELS = {
    **DOC_STATUS_LABELS,
    DOC_STATUS_DRAFT: 'Đã tạo',
    DOC_STATUS_POSTED: 'Đã xuất kho',
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

ISSUE_TYPE_LEGACY_LABELS = dict(ISSUE_TYPE_CHOICES)


def issue_type_display(value):
    """Hiển thị lý do xuất: text tự do hoặc nhãn cũ nếu còn mã legacy."""
    text = (value or '').strip()
    if not text:
        return ''
    return ISSUE_TYPE_LEGACY_LABELS.get(text, text)

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
    (TRANSFER_STATUS_CANCELLED, 'Đã hủy'),
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

# parent_code, parent_name, parent_sort, [(child_code, child_name, child_sort), ...]
DEFAULT_MATERIAL_CATEGORY_TREE = [
    (
        'vai',
        'Vải',
        1,
        [
            ('vai-chinh', 'Vải chính', 1),
            ('vai-phoi', 'Vải phối', 2),
        ],
    ),
    (
        'bo-vien',
        'Bo & viền',
        2,
        [
            ('bo-co-tay', 'Bo cổ / bo tay', 1),
        ],
    ),
    (
        'khoa-phu-kien',
        'Khóa & phụ kiện',
        3,
        [
            ('day-khoa', 'Dây kéo / dây rút / nút / khoen', 1),
        ],
    ),
    (
        'nhan-bao-bi',
        'Nhãn & bao bì',
        4,
        [
            ('tem-nhan', 'Tem nhãn / tag / size', 1),
            ('bao-bi', 'Bao bì / túi / thùng', 2),
        ],
    ),
    (
        'in-trang-tri',
        'In & trang trí',
        5,
        [
            ('decal', 'Decal / vật tư in ép', 1),
        ],
    ),
    (
        'chi-may-nhom',
        'Chỉ & may',
        6,
        [
            ('chi-may', 'Chỉ may', 1),
        ],
    ),
    (
        'khac-nhom',
        'Khác',
        7,
        [
            ('khac', 'Phụ liệu khác', 1),
        ],
    ),
]

# code, tên hiển thị, mã hex (#RRGGBB), thứ tự
DEFAULT_MATERIAL_COLORS = [
    ('den', 'Đen', '#000000', 1),
    ('trang', 'Trắng', '#FFFFFF', 2),
    ('xam-dam', 'Xám đậm', '#374151', 3),
    ('xam', 'Xám', '#6B7280', 4),
    ('xam-nhat', 'Xám nhạt', '#D1D5DB', 5),
    ('do', 'Đỏ', '#DC2626', 6),
    ('do-dam', 'Đỏ đậm', '#991B1B', 7),
    ('do-tuoi', 'Đỏ tươi', '#EF4444', 8),
    ('do-do', 'Đỏ đô', '#7F1D1D', 9),
    ('hong', 'Hồng', '#EC4899', 10),
    ('hong-nhat', 'Hồng nhạt', '#F9A8D4', 11),
    ('hong-dam', 'Hồng đậm', '#BE185D', 12),
    ('hong-san-ho', 'Hồng san hô', '#FB7185', 13),
    ('cam', 'Cam', '#F97316', 14),
    ('cam-dam', 'Cam đậm', '#C2410C', 15),
    ('cam-nhat', 'Cam nhạt', '#FDBA74', 16),
    ('vang', 'Vàng', '#EAB308', 17),
    ('vang-nhat', 'Vàng nhạt', '#FDE047', 18),
    ('vang-dong', 'Vàng đồng', '#B8860B', 19),
    ('vang-sen', 'Vàng sen', '#FBBF24', 20),
    ('kem', 'Kem', '#FFF8E7', 21),
    ('be', 'Be', '#D6C4A8', 22),
    ('xanh-la', 'Xanh lá', '#22C55E', 23),
    ('xanh-la-dam', 'Xanh lá đậm', '#15803D', 24),
    ('xanh-la-nhat', 'Xanh lá nhạt', '#86EFAC', 25),
    ('xanh-rung', 'Xanh rừng', '#166534', 26),
    ('xanh-bien', 'Xanh biển', '#0891B2', 27),
    ('xanh-ngoc', 'Xanh ngọc', '#06B6D4', 28),
    ('xanh-duong', 'Xanh dương', '#3B82F6', 29),
    ('xanh-duong-dam', 'Xanh dương đậm', '#1D4ED8', 30),
    ('xanh-duong-nhat', 'Xanh dương nhạt', '#93C5FD', 31),
    ('xanh-than', 'Xanh than', '#1E3A5F', 32),
    ('xanh-mint', 'Xanh mint', '#6EE7B7', 33),
    ('tim', 'Tím', '#8B5CF6', 34),
    ('tim-dam', 'Tím đậm', '#6D28D9', 35),
    ('tim-nhat', 'Tím nhạt', '#C4B5FD', 36),
    ('tim-than', 'Tím than', '#4C1D95', 37),
    ('nau', 'Nâu', '#92400E', 38),
    ('nau-dam', 'Nâu đậm', '#78350F', 39),
    ('nau-nhat', 'Nâu nhạt', '#A16207', 40),
    ('cafe', 'Cà phê', '#6F4E37', 41),
    ('chocolate', 'Chocolate', '#3E2723', 42),
    ('bac', 'Bạc', '#C0C0C0', 43),
    ('da', 'Da', '#E8C4A0', 44),
    ('vang-oliu', 'Vàng ô liu', '#84CC16', 45),
    ('xanh-oliu', 'Xanh ô liu', '#65A30D', 46),
    ('xanh-nga', 'Xanh ngọc lam', '#14B8A6', 47),
    ('xam-xanh', 'Xám xanh', '#64748B', 48),
    ('vang-chanh', 'Vàng chanh', '#A3E635', 49),
    ('xanh-thien', 'Xanh thiên thanh', '#7DD3FC', 50),
]

# code, tên hiển thị, thứ tự
DEFAULT_MATERIAL_SPECIFICATIONS = [
    ('kho-1m5', 'Khổ 1m5', 1),
    ('kho-1m6', 'Khổ 1m6', 2),
    ('kho-1m7', 'Khổ 1m7', 3),
    ('kho-1m8', 'Khổ 1m8', 4),
    ('kho-1m2', 'Khổ 1m2', 5),
    ('kho-30cm', 'Khổ 30cm', 6),
    ('kho-40cm', 'Khổ 40cm', 7),
    ('kho-1m', 'Khổ 1m', 8),
    ('kho-2m', 'Khổ 2m', 9),
    ('kho-60in', 'Khổ 60"', 10),
    ('kho-72in', 'Khổ 72"', 11),
    ('cuon-15kg', 'Cuộn 15kg', 12),
    ('cuon-20kg', 'Cuộn 20kg', 13),
    ('cuon-25kg', 'Cuộn 25kg', 14),
    ('cuon-50kg', 'Cuộn 50kg', 15),
    ('cuon-100m', 'Cuộn 100m', 16),
    ('cuon-3000m', 'Cuộn 3000m', 17),
    ('cuon-5000m', 'Cuộn 5000m', 18),
    ('cuon-10000m', 'Cuộn 10000m', 19),
    ('cuon-1000tem', 'Cuộn 1000 tem', 20),
    ('cuon-2000tem', 'Cuộn 2000 tem', 21),
    ('dai-15cm', 'Dài 15cm', 22),
    ('dai-20cm', 'Dài 20cm', 23),
    ('dai-25cm', 'Dài 25cm', 24),
    ('dai-30cm', 'Dài 30cm', 25),
    ('dai-50cm', 'Dài 50cm', 26),
    ('o-12mm', 'Ø 12mm', 27),
    ('o-15mm', 'Ø 15mm', 28),
    ('o-18mm', 'Ø 18mm', 29),
    ('kich-8cm', '8cm', 30),
    ('kich-10cm', '10cm', 31),
    ('kich-12cm', '12cm', 32),
    ('tui-30x40', '30×40cm', 33),
    ('tui-35x45', '35×45cm', 34),
    ('thung-60x40x40', '60×40×40cm', 35),
    ('thung-50x35x30', '50×35×30cm', 36),
    ('bo-500cai', 'Bộ 500 cái', 37),
    ('size-smlxl', 'Size S/M/L/XL', 38),
    ('goi-50', 'Gói 50', 39),
    ('goi-100', 'Gói 100', 40),
    ('goi-500', 'Gói 500', 41),
    ('hop-50', 'Hộp 50', 42),
    ('a4-sheet', 'A4 sheet', 43),
    ('met-1', '1 mét', 44),
    ('khac', 'Khác', 45),
]
