PRODUCT_TYPE_THANH_PHAM = 'thanh_pham'
PRODUCT_TYPE_HANG_HOA = 'hang_hoa'

PRODUCT_TYPE_CHOICES = [
    (PRODUCT_TYPE_THANH_PHAM, 'Thành phẩm'),
    (PRODUCT_TYPE_HANG_HOA, 'Hàng hoá'),
]

PRODUCT_TYPE_LABELS = dict(PRODUCT_TYPE_CHOICES)

SYNC_SOURCE_MANUAL = 'manual'
SYNC_SOURCE_KIOTVIET = 'kiotviet'

SYNC_SOURCE_CHOICES = [
    (SYNC_SOURCE_MANUAL, 'Nhập tay'),
    (SYNC_SOURCE_KIOTVIET, 'KiotViet'),
]

STYLE_SOURCE_MANUAL = 'manual'
STYLE_SOURCE_KIOTVIET = 'kiotviet'

STYLE_SOURCE_CHOICES = [
    (STYLE_SOURCE_MANUAL, 'Nhập tay'),
    (STYLE_SOURCE_KIOTVIET, 'KiotViet'),
]

DEFAULT_BRAND = 'JP'
# Nhóm mặc định khi loại chưa có phân nhóm (JKT → JP-JKT-00-…; SET-SC đã có nhóm sẵn)
DEFAULT_STYLE_GROUP = '00'

# Seed danh mục loại mã (TEE, SET-SC, …)
DEFAULT_CATALOG_TYPES: list[tuple[str, str, int]] = [
    ('TEE', 'Áo thun', 10),
    ('POLO', 'Áo polo', 20),
    ('JKT', 'Áo khoác', 30),
    ('TANK', 'Áo ba lỗ', 40),
    ('SHRT', 'Quần short', 50),
    ('PANT', 'Quần dài', 60),
    ('LGG', 'Legging', 70),
    ('SKT', 'Váy thể thao', 80),
    ('SET', 'Bộ sản phẩm', 90),
    ('SWM', 'Đồ bơi', 100),
    ('ACC', 'Phụ kiện', 110),
    ('SET-SC', 'Bộ bóng đá', 120),
    ('SET-VB', 'Bộ bóng chuyền', 130),
    ('SET-BB', 'Bộ bóng rổ', 140),
    ('SJY-SC', 'Áo bóng đá', 150),
    ('SJY-VB', 'Áo bóng chuyền', 160),
    ('ACC-BALO', 'Balo', 170),
    ('ACC-BAG', 'Túi', 180),
    ('ACC-SHCK', 'Vớ', 190),
    ('ACC-HAT', 'Nón/mũ', 200),
]

KV_MAP_MATCH_EXACT = 'exact'
KV_MAP_MATCH_CONTAINS = 'contains'

KV_MAP_MATCH_CHOICES = [
    (KV_MAP_MATCH_EXACT, 'Khớp đúng'),
    (KV_MAP_MATCH_CONTAINS, 'Chứa chuỗi'),
]

# ---------------------------------------------------------------------------
# Kho thành phẩm — xem docs/integrations/central-product/inventory-schema.md
# ---------------------------------------------------------------------------

WAREHOUSE_OWNER_PORTAL = 'portal'
WAREHOUSE_OWNER_SALES = 'sales'

WAREHOUSE_OWNER_CHOICES = [
    (WAREHOUSE_OWNER_PORTAL, 'Portal (xưởng)'),
    (WAREHOUSE_OWNER_SALES, 'Bán hàng'),
]

SOURCE_SYSTEM_PORTAL = 'portal'
SOURCE_SYSTEM_SALES = 'sales'

SOURCE_SYSTEM_CHOICES = [
    (SOURCE_SYSTEM_PORTAL, 'Portal'),
    (SOURCE_SYSTEM_SALES, 'Bán hàng'),
]

MOVEMENT_PRODUCTION_IN = 'production_in'
MOVEMENT_SALE_OUT = 'sale_out'
MOVEMENT_SALE_RETURN_IN = 'sale_return_in'
MOVEMENT_TRANSFER_OUT = 'transfer_out'
MOVEMENT_TRANSFER_IN = 'transfer_in'
MOVEMENT_ADJUST = 'adjust'
MOVEMENT_DISPOSAL_OUT = 'disposal_out'

MOVEMENT_KIND_CHOICES = [
    (MOVEMENT_PRODUCTION_IN, 'Nhập thành phẩm'),
    (MOVEMENT_SALE_OUT, 'Xuất bán'),
    (MOVEMENT_SALE_RETURN_IN, 'Khách trả'),
    (MOVEMENT_TRANSFER_OUT, 'Chuyển đi'),
    (MOVEMENT_TRANSFER_IN, 'Chuyển đến'),
    (MOVEMENT_ADJUST, 'Điều chỉnh / kiểm kê'),
    (MOVEMENT_DISPOSAL_OUT, 'Xuất hủy'),
]

# Dấu bắt buộc của qty_delta theo từng loại: 1 = phải dương, -1 = phải âm,
# 0 = tùy (chỉ điều chỉnh/kiểm kê mới được cả hai chiều).
# Không có bảng này thì một phát sinh 'sale_out' mang số dương sẽ âm thầm
# làm phồng tồn thay vì báo lỗi.
MOVEMENT_DIRECTION = {
    MOVEMENT_PRODUCTION_IN: 1,
    MOVEMENT_SALE_OUT: -1,
    MOVEMENT_SALE_RETURN_IN: 1,
    MOVEMENT_TRANSFER_OUT: -1,
    MOVEMENT_TRANSFER_IN: 1,
    MOVEMENT_ADJUST: 0,
    MOVEMENT_DISPOSAL_OUT: -1,
}

DOC_TYPE_FG_RECEIPT = 'fg_receipt'
DOC_TYPE_INVOICE = 'invoice'
DOC_TYPE_SALE_RETURN = 'sale_return'
DOC_TYPE_TRANSFER = 'transfer'
DOC_TYPE_STOCKTAKE = 'stocktake'
DOC_TYPE_DISPOSAL = 'disposal'

DOC_TYPE_CHOICES = [
    (DOC_TYPE_FG_RECEIPT, 'Yêu cầu nhập thành phẩm'),
    (DOC_TYPE_INVOICE, 'Hóa đơn bán'),
    (DOC_TYPE_SALE_RETURN, 'Phiếu trả hàng'),
    (DOC_TYPE_TRANSFER, 'Phiếu chuyển kho'),
    (DOC_TYPE_STOCKTAKE, 'Phiếu kiểm kê'),
    (DOC_TYPE_DISPOSAL, 'Phiếu hủy'),
]

# Mã kho seed — chốt ngày 20/08/2026, toàn hệ chỉ có 2 địa điểm.
DEFAULT_WAREHOUSES: list[tuple[str, str, str]] = [
    ('XUONG-TP', 'Kho thành phẩm — Xưởng sản xuất', WAREHOUSE_OWNER_PORTAL),
    ('CH-TRUNG-TAM', 'Chi nhánh trung tâm', WAREHOUSE_OWNER_SALES),
]
