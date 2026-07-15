"""Cột bảng tồn kho — hiển thị và localStorage."""

STOCK_LIST_COLUMNS = [
    {'key': 'image', 'label': 'Ảnh', 'default': True, 'required': True, 'weight': 40, 'sortable': False},
    {'key': 'code', 'label': 'Mã', 'default': True, 'required': True, 'weight': 100},
    {'key': 'name', 'label': 'Tên NPL', 'default': True, 'required': False, 'weight': 150},
    {'key': 'category', 'label': 'Nhóm', 'default': True, 'required': False, 'weight': 120},
    {'key': 'color', 'label': 'Màu', 'default': True, 'required': False, 'weight': 100},
    {'key': 'unit', 'label': 'ĐVT', 'default': True, 'required': False, 'weight': 35},
    {'key': 'total_qty', 'label': 'Tồn hiện tại', 'default': True, 'required': False, 'weight': 120},
    {'key': 'avg_unit_price', 'label': 'Đơn giá BQ', 'default': True, 'required': False, 'weight': 100},
    {'key': 'stock_value', 'label': 'Giá trị tồn', 'default': True, 'required': False, 'weight': 110},
    {'key': 'min_stock', 'label': 'Tối thiểu', 'default': True, 'required': False, 'weight': 80},
    {'key': 'stock_status', 'label': 'Trạng thái', 'default': True, 'required': False, 'weight': 90},
    {'key': 'detail', 'label': 'Chi tiết', 'default': True, 'required': False, 'weight': 80, 'sortable': False},
]

STOCK_LIST_TOTAL_COL_WEIGHT = sum(c['weight'] for c in STOCK_LIST_COLUMNS)

STOCK_LIST_SORT_FIELDS = {
    'code': lambda r: (r['material'].code or '').lower(),
    'name': lambda r: (r['material'].name or '').lower(),
    'category': lambda r: (r['material'].category.name or '').lower(),
    'color': lambda r: (r['material'].color.name if r['material'].color_id else '').lower(),
    'unit': lambda r: (r['material'].unit.name or '').lower(),
    'total_qty': lambda r: r['total_qty'],
    'avg_unit_price': lambda r: r.get('avg_unit_price') or 0,
    'stock_value': lambda r: r.get('stock_value') or 0,
    'min_stock': lambda r: r['material'].min_stock,
    'stock_status': lambda r: r['status'],
}
