"""Bảng thông số kích thước: size cố định, ô có nội dung là size đưa vào Thư viện."""

from __future__ import annotations

import re

SIZE_SPEC_SIZES = (
    '1', '3', '5', '7', '9', '11', '13', '15',
    'S', 'M', 'L', 'XL', '2XL', '3XL', '4XL', '5XL', '6XL',
)

_LINE = re.compile(
    r'^(6XL|5XL|4XL|3XL|2XL|XL|11|13|15|1|3|5|7|9|S|M|L)\s*[:：\t]\s*(.*)$',
    re.IGNORECASE,
)


def parse_size_spec(text: str) -> dict[str, str]:
    notes = {size: '' for size in SIZE_SPEC_SIZES}
    for raw in (text or '').splitlines():
        line = raw.strip()
        if not line:
            continue
        match = _LINE.match(line)
        if not match:
            continue
        size = match.group(1).upper()
        if size in notes and not notes[size]:
            notes[size] = match.group(2).strip()
    return notes


def format_size_spec(notes: dict[str, str]) -> str:
    lines = []
    for size in SIZE_SPEC_SIZES:
        note = (notes.get(size) or '').strip()
        if note:
            lines.append(f'{size}: {note}')
    return '\n'.join(lines)


def size_spec_from_post(post) -> str:
    notes = {
        size: (post.get(f'size_note_{size}') or '').strip()
        for size in SIZE_SPEC_SIZES
    }
    return format_size_spec(notes)


def filled_sizes(text: str) -> list[str]:
    notes = parse_size_spec(text)
    return [size for size in SIZE_SPEC_SIZES if notes[size]]


def size_cells(text: str) -> list[dict[str, str]]:
    notes = parse_size_spec(text)
    return [{'code': size, 'note': notes[size]} for size in SIZE_SPEC_SIZES]
