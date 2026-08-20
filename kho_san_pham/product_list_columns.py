PRODUCT_LIST_COLUMNS = [
    {'key': 'image', 'label': 'Ảnh', 'default': True, 'required': True, 'weight': 40, 'sortable': False},
    {'key': 'code', 'label': 'SKU', 'default': True, 'required': True, 'weight': 140},
    {'key': 'style_code', 'label': 'Style', 'default': True, 'required': False, 'weight': 110},
    {'key': 'color_code', 'label': 'Màu', 'default': True, 'required': False, 'weight': 70},
    {'key': 'size_label', 'label': 'Size', 'default': True, 'required': False, 'weight': 50},
    {'key': 'accounting_code', 'label': 'Mã KT', 'default': False, 'required': False, 'weight': 90},
    {'key': 'kiotviet_code', 'label': 'Mã KV', 'default': True, 'required': False, 'weight': 90},
    {'key': 'name', 'label': 'Tên', 'default': True, 'required': False, 'weight': 140},
    {'key': 'product_type', 'label': 'Loại', 'default': True, 'required': False, 'weight': 80},
    {'key': 'unit', 'label': 'ĐVT', 'default': False, 'required': False, 'weight': 50},
    {'key': 'base_price', 'label': 'Giá', 'default': True, 'required': False, 'weight': 80},
    {'key': 'qty_on_hand', 'label': 'Tồn kho', 'default': True, 'required': False, 'weight': 70},
    {'key': 'status', 'label': 'Trạng thái', 'default': True, 'required': False, 'weight': 80},
]

PRODUCT_LIST_TOTAL_COL_WEIGHT = sum(c['weight'] for c in PRODUCT_LIST_COLUMNS)

PRODUCT_LIST_SORT_FIELDS = {
    'code': 'code',
    'style_code': 'style_code',
    'color_code': 'color_code',
    'size_label': 'size_label',
    'accounting_code': 'accounting_code',
    'kiotviet_code': 'kiotviet_code',
    'name': 'name',
    'product_type': 'product_type',
    'unit': 'unit',
    'base_price': 'base_price',
    'qty_on_hand': 'qty_on_hand',
    'status': 'is_active',
}
