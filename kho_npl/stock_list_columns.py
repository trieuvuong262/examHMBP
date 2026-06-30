"""Cột bảng tồn kho — hiển thị và localStorage."""

STOCK_LIST_COLUMNS = [
    {'key': 'code', 'label': 'Mã', 'default': True, 'required': True, 'weight': 100},
    {'key': 'name', 'label': 'Tên NPL', 'default': True, 'required': False, 'weight': 150},
    {'key': 'category_parent', 'label': 'Nhóm cấp 1', 'default': True, 'required': False, 'weight': 100},
    {'key': 'category', 'label': 'Nhóm cấp 2', 'default': True, 'required': False, 'weight': 100},
    {'key': 'color', 'label': 'Màu', 'default': True, 'required': False, 'weight': 100},
    {'key': 'unit', 'label': 'ĐVT', 'default': True, 'required': False, 'weight': 50},
    {'key': 'total_qty', 'label': 'Tồn hiện tại', 'default': True, 'required': False, 'weight': 100},
    {'key': 'min_stock', 'label': 'Tối thiểu', 'default': True, 'required': False, 'weight': 50},
    {'key': 'primary_location', 'label': 'Vị trí chính', 'default': True, 'required': False, 'weight': 100},
    {'key': 'stock_status', 'label': 'Trạng thái', 'default': True, 'required': False, 'weight': 50},
]

STOCK_LIST_TOTAL_COL_WEIGHT = sum(c['weight'] for c in STOCK_LIST_COLUMNS)

STOCK_LIST_SORT_FIELDS = {
    'code': lambda r: (r['material'].code or '').lower(),
    'name': lambda r: (r['material'].name or '').lower(),
    'category_parent': lambda r: (r['material'].category.parent.name if r['material'].category and r['material'].category.parent_id else '').lower(),
    'category': lambda r: (r['material'].category.name or '').lower(),
    'color': lambda r: (r['material'].color.name if r['material'].color_id else '').lower(),
    'unit': lambda r: (r['material'].unit.name or '').lower(),
    'total_qty': lambda r: r['total_qty'],
    'min_stock': lambda r: r['material'].min_stock,
    'primary_location': lambda r: (r['primary_location'] or '').lower(),
    'stock_status': lambda r: r['status'],
}
