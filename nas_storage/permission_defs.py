"""Định nghĩa quyền chi tiết — khớp Permission Editor trên Synology DSM."""

PERM_TYPE_ALLOW = 'allow'
PERM_TYPE_DENY = 'deny'
PERM_TYPE_CHOICES = (
    (PERM_TYPE_ALLOW, 'Allow'),
    (PERM_TYPE_DENY, 'Deny'),
)

APPLY_ALL = 'all'
APPLY_FOLDER = 'folder'
APPLY_SUBFOLDERS = 'subfolders'
APPLY_FILES = 'files'
APPLY_TO_CHOICES = (
    (APPLY_ALL, 'This folder, sub-folders and files'),
    (APPLY_FOLDER, 'This folder'),
    (APPLY_SUBFOLDERS, 'Sub-folders'),
    (APPLY_FILES, 'Files'),
)

READ_FIELDS = (
    ('perm_traverse', 'Traverse folders/Execute files'),
    ('perm_list_read', 'List folders/Read data'),
    ('perm_read_attr', 'Read attributes'),
    ('perm_read_ext_attr', 'Read extended attributes'),
    ('perm_read_acl', 'Read permissions'),
)

WRITE_FIELDS = (
    ('perm_create_files', 'Create files/Write data'),
    ('perm_create_folders', 'Create folders/Append data'),
    ('perm_write_attr', 'Write attributes'),
    ('perm_write_ext_attr', 'Write extended attributes'),
    ('perm_delete_children', 'Delete subfolders and files'),
    ('perm_delete', 'Delete'),
)

ADMIN_FIELDS = (
    ('perm_change_acl', 'Change permissions'),
    ('perm_take_ownership', 'Take ownership'),
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
    """Đọc + tạo/ghi — không xóa và không di chuyển (SMB cần quyền xóa để cắt/đổi tên)."""
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
    'read': 'Read',
    'read_write_no_delete': 'Read & Write (no Delete)',
    'read_write': 'Read & Write',
    'full': 'Full Control',
    'custom': 'Custom',
}

PRESET_FORM_CHOICES = (
    ('read', 'Read'),
    ('read_write', 'Read & Write'),
    ('full', 'Full Control'),
    ('read_write_no_delete', 'Read & Write (no Delete)'),
    ('', 'Custom'),
)


def preset_flags_map() -> dict[str, dict[str, bool]]:
    return {
        'read': flags_from_preset('read'),
        'read_write': flags_from_preset('read_write'),
        'read_write_no_delete': flags_from_preset('read_write_no_delete'),
        'full': flags_from_preset('full'),
    }


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
    """Đổi mọi bản ghi Portal đang «Đọc + Ghi (được di chuyển)» sang không xóa. Giữ full / chỉ đọc."""
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


def convert_no_delete_permissions_to_read_write() -> int:
    """Đổi «không xóa» sang đọc+ghi có xóa — SMB mới di chuyển/đổi tên được. Giữ full / chỉ đọc."""
    from nas_storage.models import NasFolderPermission

    flags = default_read_write_flags()
    updated = 0
    for perm in NasFolderPermission.objects.iterator():
        if detect_preset_from_flags(perm.permission_flags()) != 'read_write_no_delete':
            continue
        for name, value in flags.items():
            setattr(perm, name, value)
        perm.save(update_fields=[*ALL_PERM_FIELD_NAMES, 'updated_at'])
        updated += 1
    return updated
