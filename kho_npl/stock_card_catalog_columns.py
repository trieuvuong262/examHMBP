"""Cột bảng danh mục chọn NPL trên màn Thẻ kho."""

STOCK_CARD_CATALOG_COLUMNS = [
    {'key': 'code', 'label': 'Mã', 'default': True, 'required': True, 'weight': 100},
    {'key': 'name', 'label': 'Tên NPL', 'default': True, 'required': False, 'weight': 150},
    {'key': 'category', 'label': 'Nhóm', 'default': True, 'required': False, 'weight': 150},
    {'key': 'specification', 'label': 'Quy cách', 'default': True, 'required': False, 'weight': 100},
    {'key': 'stock_total', 'label': 'Tồn', 'default': True, 'required': False, 'weight': 100},
]

STOCK_CARD_CATALOG_TOTAL_COL_WEIGHT = sum(c['weight'] for c in STOCK_CARD_CATALOG_COLUMNS)

STOCK_CARD_CATALOG_SORT_FIELDS = {
    'code': 'code',
    'name': 'name',
    'category': 'category__name',
    'specification': 'specification',
    'stock_total': 'stock_total',
}
