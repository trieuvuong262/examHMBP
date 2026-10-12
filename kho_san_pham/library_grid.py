"""Cột bảng Thư viện sản phẩm (theo Style) — đăng ký vào bộ lưới chung của Sản xuất."""

from san_xuat.list_grid import SX_LIST_GRIDS, _col, _cols, _spec

LIST_KEY = 'ksp_library'

SX_LIST_GRIDS[LIST_KEY] = _spec(
    _cols(
        _col('name', 'Sản phẩm', weight=240, required=True),
        _col('style_code', 'Style', weight=130, default=False),
        _col('group', 'Nhóm', weight=120, sortable=False),
        _col('sku_count', 'SKU', weight=60, align='end'),
        _col('colors', 'Màu', weight=130, sortable=False),
        _col('sizes', 'Size', weight=110, sortable=False),
        _col('price', 'Giá bán', weight=110, align='end'),
        _col('channel', 'KiotViet', weight=95, sortable=False),
        _col('dossier', 'Hồ sơ thiết kế', weight=110, sortable=False),
        _col('status', 'Trạng thái', weight=95, sortable=False),
        _col('last_update', 'Cập nhật', weight=100),
        meta=False,
    ),
    {
        'name': 'style_code',
        'style_code': 'style_code',
        'sku_count': 'sku_count',
        'price': 'min_price',
        'last_update': 'last_update',
    },
    default_sort='last_update',
)
