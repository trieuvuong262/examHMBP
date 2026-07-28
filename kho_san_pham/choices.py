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
