"""Định nghĩa quyền chi tiết — khớp Permission Editor trên Synology DSM."""

PERM_TYPE_ALLOW = 'allow'
PERM_TYPE_DENY = 'deny'
PERM_TYPE_CHOICES = (
    (PERM_TYPE_ALLOW, 'Cho phép'),
    (PERM_TYPE_DENY, 'Từ chối'),
)

APPLY_ALL = 'all'
APPLY_FOLDER = 'folder'
APPLY_SUBFOLDERS = 'subfolders'
APPLY_FILES = 'files'
APPLY_TO_CHOICES = (
    (APPLY_ALL, 'Tất cả'),
    (APPLY_FOLDER, 'Chỉ thư mục này'),
    (APPLY_SUBFOLDERS, 'Chỉ thư mục con'),
    (APPLY_FILES, 'Chỉ tệp'),
)

READ_FIELDS = (
    ('perm_traverse', 'Duyệt thư mục / Thực thi tệp'),
    ('perm_list_read', 'Liệt kê thư mục / Đọc dữ liệu'),
    ('perm_read_attr', 'Đọc thuộc tính'),
    ('perm_read_ext_attr', 'Đọc thuộc tính mở rộng'),
    ('perm_read_acl', 'Đọc quyền'),
)

WRITE_FIELDS = (
    ('perm_create_files', 'Tạo tệp / Ghi dữ liệu'),
    ('perm_create_folders', 'Tạo thư mục / Ghi thêm dữ liệu'),
    ('perm_write_attr', 'Ghi thuộc tính'),
    ('perm_write_ext_attr', 'Ghi thuộc tính mở rộng'),
    ('perm_delete_children', 'Xóa thư mục con và tệp'),
    ('perm_delete', 'Xóa'),
)

ADMIN_FIELDS = (
    ('perm_change_acl', 'Thay đổi quyền'),
    ('perm_take_ownership', 'Chiếm quyền sở hữu'),
)

ALL_PERM_FIELD_NAMES = tuple(
    name for name, _ in (*READ_FIELDS, *WRITE_FIELDS, *ADMIN_FIELDS)
)


def default_read_write_flags() -> dict[str, bool]:
    """Mặc định giống ảnh: đủ Read + Write, không Administration."""
    flags = {name: False for name in ALL_PERM_FIELD_NAMES}
    for name, _ in READ_FIELDS:
        flags[name] = True
    for name, _ in WRITE_FIELDS:
        flags[name] = True
    return flags


def flags_from_preset(preset: str) -> dict[str, bool]:
    flags = {name: False for name in ALL_PERM_FIELD_NAMES}
    if preset == 'read':
        for name, _ in READ_FIELDS:
            flags[name] = True
    elif preset == 'read_write':
        flags.update(default_read_write_flags())
    elif preset == 'full':
        for name in ALL_PERM_FIELD_NAMES:
            flags[name] = True
    return flags


def has_write_access(flags: dict[str, bool]) -> bool:
    return any(flags.get(name) for name, _ in WRITE_FIELDS)


def has_read_access(flags: dict[str, bool]) -> bool:
    return any(flags.get(name) for name, _ in READ_FIELDS)
