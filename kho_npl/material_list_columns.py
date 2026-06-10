"""Cột bảng danh mục nguyên phụ liệu — dùng cho hiển thị và lưu localStorage."""

MATERIAL_LIST_COLUMNS = [
    {'key': 'code', 'label': 'Mã', 'default': True, 'required': True},
    {'key': 'name', 'label': 'Tên NPL', 'default': True, 'required': False},
    {'key': 'category', 'label': 'Nhóm', 'default': True, 'required': False},
    {'key': 'color', 'label': 'Màu', 'default': True, 'required': False},
    {'key': 'specification', 'label': 'Quy cách', 'default': True, 'required': False},
    {'key': 'unit', 'label': 'ĐVT', 'default': True, 'required': False},
    {'key': 'supplier', 'label': 'NCC', 'default': True, 'required': False},
    {'key': 'min_stock', 'label': 'Tối thiểu', 'default': True, 'required': False},
    {'key': 'status', 'label': 'Trạng thái', 'default': True, 'required': False},
]

MATERIAL_LIST_COLUMN_KEYS = {c['key'] for c in MATERIAL_LIST_COLUMNS}
MATERIAL_LIST_DEFAULT_VISIBLE = {c['key'] for c in MATERIAL_LIST_COLUMNS if c['default']}
MATERIAL_LIST_REQUIRED_KEYS = {c['key'] for c in MATERIAL_LIST_COLUMNS if c.get('required')}

MATERIAL_LIST_SORT_FIELDS = {
    'code': 'code',
    'name': 'name',
    'category': 'category__name',
    'color': 'color',
    'specification': 'specification',
    'unit': 'unit__name',
    'supplier': 'supplier__name',
    'min_stock': 'min_stock',
    'status': 'is_active',
}
