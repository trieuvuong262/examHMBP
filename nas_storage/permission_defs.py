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


WRITE_NO_DELETE_FIELD_NAMES = (
    'perm_create_files',
    'perm_create_folders',
    'perm_write_attr',
    'perm_write_ext_attr',
)
DELETE_FIELD_NAMES = (
    'perm_delete_children',
    'perm_delete',
)


def default_read_write_flags() -> dict[str, bool]:
    """Đọc + ghi gồm xóa — không Administration."""
    flags = {name: False for name in ALL_PERM_FIELD_NAMES}
    for name, _ in READ_FIELDS:
        flags[name] = True
    for name, _ in WRITE_FIELDS:
        flags[name] = True
    return flags


def default_read_write_no_delete_flags() -> dict[str, bool]:
    """Đọc + tạo/ghi tệp thư mục — không xóa, không Administration."""
    flags = {name: False for name in ALL_PERM_FIELD_NAMES}
    for name, _ in READ_FIELDS:
        flags[name] = True
    for name in WRITE_NO_DELETE_FIELD_NAMES:
        flags[name] = True
    return flags


def flags_from_preset(preset: str) -> dict[str, bool]:
    flags = {name: False for name in ALL_PERM_FIELD_NAMES}
    if preset == 'read':
        for name, _ in READ_FIELDS:
            flags[name] = True
    elif preset == 'read_write_no_delete':
        flags.update(default_read_write_no_delete_flags())
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


PRESET_LABELS = {
    'read': 'Chỉ đọc',
    'read_write_no_delete': 'Đọc + Ghi (không xóa)',
    'read_write': 'Đọc + Ghi (gồm xóa)',
    'full': 'Đầy đủ',
    'custom': 'Tuỳ chỉnh',
}

PRESET_FORM_CHOICES = (
    ('read_write_no_delete', 'Đọc + Ghi (không xóa)'),
    ('read_write', 'Đọc + Ghi (gồm xóa)'),
    ('read', 'Chỉ đọc'),
    ('full', 'Đầy đủ (quản trị)'),
    ('', 'Tuỳ chỉnh nâng cao'),
)

# synoacltool ACL Perm: rwxpdDaARWcCo
SYNOACL_PERM_BITS = (
    ('perm_list_read', 'r'),
    ('perm_create_files', 'w'),
    ('perm_traverse', 'x'),
    ('perm_create_folders', 'p'),
    ('perm_delete', 'd'),
    ('perm_delete_children', 'D'),
    ('perm_read_attr', 'a'),
    ('perm_write_attr', 'A'),
    ('perm_read_ext_attr', 'R'),
    ('perm_write_ext_attr', 'W'),
    ('perm_read_acl', 'c'),
    ('perm_change_acl', 'C'),
    ('perm_take_ownership', 'o'),
)


def synoacl_mask_from_flags(flags: dict[str, bool], *, inherit: str = 'fd--') -> str:
    bits = ''.join(ch if flags.get(name) else '-' for name, ch in SYNOACL_PERM_BITS)
    return f'{bits}:{inherit}'


def detect_preset_from_flags(flags: dict[str, bool]) -> str:
    if all(flags.get(name) for name in ALL_PERM_FIELD_NAMES):
        return 'full'
    rw = default_read_write_flags()
    if all(flags.get(name) == value for name, value in rw.items()):
        return 'read_write'
    no_delete = default_read_write_no_delete_flags()
    if all(flags.get(name) == value for name, value in no_delete.items()):
        return 'read_write_no_delete'
    read_only = (
        all(flags.get(name) for name, _ in READ_FIELDS)
        and not any(flags.get(name) for name, _ in WRITE_FIELDS)
        and not any(flags.get(name) for name, _ in ADMIN_FIELDS)
    )
    if read_only:
        return 'read'
    return 'custom'


def access_level_label(flags: dict[str, bool]) -> str:
    return PRESET_LABELS.get(detect_preset_from_flags(flags), PRESET_LABELS['custom'])


def convert_read_write_permissions_to_no_delete() -> int:
    """Đổi mọi bản ghi Portal đang «Đọc + Ghi (gồm xóa)» sang không xóa. Giữ full / chỉ đọc."""
    from nas_storage.models import NasFolderPermission

    flags = default_read_write_no_delete_flags()
    updated = 0
    for perm in NasFolderPermission.objects.iterator():
        if detect_preset_from_flags(perm.permission_flags()) != 'read_write':
            continue
        for name, value in flags.items():
            setattr(perm, name, value)
        perm.save(update_fields=[*ALL_PERM_FIELD_NAMES, 'updated_at'])
        updated += 1
    return updated
