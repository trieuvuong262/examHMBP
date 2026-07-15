from kho_npl.forms import (
    MaterialCategoryForm,
    MaterialColorForm,
    MaterialSpecificationForm,
    SupplierForm,
    UnitForm,
    WarehouseLocationForm,
)
from kho_npl.models import (
    MaterialCategory,
    MaterialColor,
    MaterialSpecification,
    Supplier,
    Unit,
    WarehouseLocation,
)

SETTINGS_SECTIONS = {
    'nhom': {
        'title': 'Nhóm nguyên phụ liệu',
        'icon': 'bi-collection',
        'model': MaterialCategory,
        'form_class': MaterialCategoryForm,
        'search_fields': ('code', 'name'),
        'order_by': ('sort_order', 'name'),
        'list_columns': (
            ('name', 'Tên nhóm'),
            ('code', 'Mã'),
            ('sort_order', 'Thứ tự'),
        ),
    },
    'dvt': {
        'title': 'Đơn vị tính',
        'icon': 'bi-rulers',
        'model': Unit,
        'form_class': UnitForm,
        'search_fields': ('code', 'name'),
        'order_by': ('name',),
        'list_columns': (
            ('code', 'Mã'),
            ('name', 'Tên ĐVT'),
        ),
    },
    'mau': {
        'title': 'Màu sắc',
        'icon': 'bi-palette',
        'model': MaterialColor,
        'form_class': MaterialColorForm,
        'search_fields': ('code', 'name', 'hex_code'),
        'order_by': ('sort_order', 'name'),
        'list_columns': (
            ('name', 'Tên màu'),
            ('hex_code', 'Mã hex'),
            ('sort_order', 'Thứ tự'),
        ),
    },
    'quy-cach': {
        'title': 'Quy cách / khổ',
        'icon': 'bi-aspect-ratio',
        'model': MaterialSpecification,
        'form_class': MaterialSpecificationForm,
        'search_fields': ('code', 'name'),
        'order_by': ('sort_order', 'name'),
        'list_columns': (
            ('name', 'Quy cách / khổ'),
            ('code', 'Mã'),
            ('sort_order', 'Thứ tự'),
        ),
    },
    'vi-tri': {
        'title': 'Vị trí kho',
        'icon': 'bi-geo-alt',
        'model': WarehouseLocation,
        'form_class': WarehouseLocationForm,
        'search_fields': ('code', 'name'),
        'order_by': ('code',),
        'list_columns': (
            ('code', 'Mã'),
            ('name', 'Tên vị trí'),
        ),
    },
    'ncc': {
        'title': 'Nhà cung cấp',
        'icon': 'bi-truck',
        'model': Supplier,
        'form_class': SupplierForm,
        'search_fields': ('code', 'name', 'phone'),
        'order_by': ('name',),
        'list_columns': (
            ('code', 'Mã'),
            ('name', 'Tên NCC'),
            ('phone', 'Điện thoại'),
        ),
    },
}


def get_settings_section(section: str):
    config = SETTINGS_SECTIONS.get(section)
    if not config:
        return None
    return {'key': section, **config}
