"""Cột bảng danh sách hồ sơ — đăng ký vào bộ lưới chung của Sản xuất."""

from san_xuat.list_grid import SX_LIST_GRIDS, _col, _cols, _spec

LIST_KEY = 'tksp_dossiers'

SX_LIST_GRIDS[LIST_KEY] = _spec(
    _cols(
        _col('name', 'Sản phẩm', weight=230, required=True),
        _col('code', 'Mã hồ sơ', weight=105, default=False),
        _col('group', 'Nhóm', weight=105),
        _col('collection', 'Mùa', weight=90, default=False),
        _col('status', 'Giai đoạn', weight=140),
        _col('owner', 'Phụ trách', weight=110),
        _col('progress', 'Tiến độ', weight=105, sortable=False),
        _col('assignee', 'Đang chờ', weight=110, default=False),
        _col('step_due', 'Hạn bước', weight=130),
        _col('late', 'Trễ', weight=55, align='end', default=False),
        _col('launch_date', 'Ra mắt', weight=85),
        _col('priority', 'Ưu tiên', weight=80, default=False),
        _col('official_code', 'Mã chính thức', weight=95, default=False),
        meta=True,
    ),
    {
        'code': 'code',
        'name': 'name',
        'group': 'product_group',
        'collection': 'collection',
        'status': 'status',
        'owner': 'owner__profile__full_name',
        'assignee': 'step_assignee_name',
        'step_due': 'step_due_at',
        'late': 'step_due_at',
        'launch_date': 'launch_date',
        'priority': 'priority_rank',
        'official_code': 'official_product_code',
        'created_by': 'proposer__profile__full_name',
        'created_at': 'created_at',
    },
    default_sort='created_at',
)
