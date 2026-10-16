"""Bảng thông số kích thước: size được tick là size đưa vào Thư viện."""

from __future__ import annotations

import re

SIZE_NUMBER = ('1', '3', '5', '7', '9', '11', '13', '15')
SIZE_LETTER = ('S', 'M', 'L', 'XL', '2XL', '3XL', '4XL', '5XL', '6XL')
SIZE_SPEC_SIZES = SIZE_NUMBER + SIZE_LETTER
SIZE_GROUPS = (
    ('number', 'Size số', SIZE_NUMBER),
    ('letter', 'Size chữ', SIZE_LETTER),
)

_LINE = re.compile(
    r'^(6XL|5XL|4XL|3XL|2XL|XL|11|13|15|1|3|5|7|9|S|M|L)\s*[:：\t]\s*(.*)$',
    re.IGNORECASE,
)


def parse_size_spec(text: str) -> dict[str, str]:
    """Size có dòng trong bảng. Giá trị là thông số, có thể rỗng."""
    notes: dict[str, str] = {}
    known = set(SIZE_SPEC_SIZES)
    for raw in (text or '').splitlines():
        line = raw.strip()
        if not line:
            continue
        match = _LINE.match(line)
        if not match:
            continue
        size = match.group(1).upper()
        if size in known and size not in notes:
            notes[size] = match.group(2).strip()
    return notes


def format_size_spec(notes: dict[str, str]) -> str:
    lines = []
    for size in SIZE_SPEC_SIZES:
        if size not in notes:
            continue
        note = (notes.get(size) or '').strip()
        lines.append(f'{size}: {note}' if note else f'{size}:')
    return '\n'.join(lines)


def size_spec_from_post(post) -> str:
    notes = {}
    for size in SIZE_SPEC_SIZES:
        if post.get(f'size_on_{size}'):
            notes[size] = (post.get(f'size_note_{size}') or '').strip()
    return format_size_spec(notes)


def filled_sizes(text: str) -> list[str]:
    notes = parse_size_spec(text)
    return [size for size in SIZE_SPEC_SIZES if size in notes]


def size_cells(text: str) -> list[dict]:
    notes = parse_size_spec(text)
    return [
        {'code': size, 'note': notes.get(size, ''), 'on': size in notes}
        for size in SIZE_SPEC_SIZES
    ]


def size_groups(text: str, *, selected_only: bool = False) -> list[dict]:
    cells = {cell['code']: cell for cell in size_cells(text)}
    groups = []
    for _key, label, codes in SIZE_GROUPS:
        rows = [cells[code] for code in codes]
        if selected_only:
            rows = [cell for cell in rows if cell['on']]
        if rows:
            groups.append({'label': label, 'cells': rows})
    return groups
