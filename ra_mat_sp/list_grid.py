"""Cột bảng danh sách kế hoạch ra mắt — đăng ký vào bộ lưới chung của Sản xuất."""

from san_xuat.list_grid import SX_LIST_GRIDS, _col, _cols, _spec

LIST_KEY = 'rmsp_plans'

SX_LIST_GRIDS[LIST_KEY] = _spec(
    _cols(
        _col('name', 'Kế hoạch', weight=240, required=True),
        _col('code', 'Mã', weight=105, default=False),
        _col('launch_date', 'Ngày ra mắt', weight=110),
        _col('products', 'Sản phẩm', weight=75, align='end', sortable=False),
        _col('coordinator', 'Điều phối', weight=120),
        _col('approver', 'Người duyệt', weight=120, default=False),
        _col('status', 'Trạng thái', weight=130),
        _col('ready', 'Sẵn sàng', weight=150, sortable=False),
        _col('alert', 'Cảnh báo', weight=150, sortable=False),
        _col('target_qty', 'SL mục tiêu', weight=90, align='end', default=False),
        _col('target_revenue', 'DT mục tiêu', weight=110, align='end', default=False),
        meta=True,
    ),
    {
        'code': 'code',
        'name': 'name',
        'launch_date': 'launch_date',
        'coordinator': 'coordinator__profile__full_name',
        'approver': 'approver__profile__full_name',
        'status': 'status',
        'target_qty': 'target_qty',
        'target_revenue': 'target_revenue',
        'created_by': 'created_by__profile__full_name',
        'created_at': 'created_at',
    },
    default_sort='launch_date',
)
