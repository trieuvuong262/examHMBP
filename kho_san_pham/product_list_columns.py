PRODUCT_LIST_COLUMNS = [
    {'key': 'image', 'label': 'Ảnh', 'default': True, 'required': True, 'weight': 40, 'sortable': False},
    {'key': 'code', 'label': 'Mã SP', 'default': True, 'required': True, 'weight': 100},
    {'key': 'accounting_code', 'label': 'Mã KT', 'default': True, 'required': False, 'weight': 90},
    {'key': 'kiotviet_code', 'label': 'Mã KV', 'default': True, 'required': False, 'weight': 90},
    {'key': 'name', 'label': 'Tên', 'default': True, 'required': False, 'weight': 160},
    {'key': 'product_type', 'label': 'Loại', 'default': True, 'required': False, 'weight': 80},
    {'key': 'unit', 'label': 'ĐVT', 'default': True, 'required': False, 'weight': 50},
    {'key': 'category', 'label': 'Nhóm', 'default': True, 'required': False, 'weight': 120},
    {'key': 'base_price', 'label': 'Giá', 'default': True, 'required': False, 'weight': 80},
    {'key': 'status', 'label': 'Trạng thái', 'default': True, 'required': False, 'weight': 90},
]

PRODUCT_LIST_TOTAL_COL_WEIGHT = sum(c['weight'] for c in PRODUCT_LIST_COLUMNS)

PRODUCT_LIST_SORT_FIELDS = {
    'code': 'code',
    'accounting_code': 'accounting_code',
    'kiotviet_code': 'kiotviet_code',
    'name': 'name',
    'product_type': 'product_type',
    'unit': 'unit',
    'category': 'category_name',
    'base_price': 'base_price',
    'status': 'is_active',
}
