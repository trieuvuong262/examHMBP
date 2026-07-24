"""Chuẩn hóa tên món — gộp «cơm Chay» / «Cơm chay» thành một."""

from __future__ import annotations

from collections import Counter


def dish_label_key(name: str | None) -> str:
    """Khóa so khớp không phân biệt hoa/thường, gộp khoảng trắng."""
    return ' '.join((name or '').casefold().split())


def normalize_dish_display(name: str | None) -> str:
    """Chuẩn khoảng trắng khi lưu snapshot / danh mục."""
    return ' '.join((name or '').split())


def pick_dish_display(names: list[str]) -> str:
    """Chọn tên hiển thị đại diện trong nhóm trùng (không phân biệt hoa/thường)."""
    cleaned = [normalize_dish_display(n) for n in names if n and str(n).strip()]
    if not cleaned:
        return ''
    return Counter(cleaned).most_common(1)[0][0]


def merge_counts_by_label(rows: list[dict], *, name_key: str = 'dish', count_key: str = 'count') -> list[dict]:
    """Gộp list {dish, count, ...} theo dish_label_key."""
    buckets: dict[str, dict] = {}
    for row in rows:
        raw = row.get(name_key) or ''
        key = dish_label_key(raw)
        if not key:
            continue
        if key not in buckets:
            buckets[key] = {'names': [], 'count': 0, 'row': dict(row)}
        buckets[key]['names'].append(raw)
        buckets[key]['count'] += int(row.get(count_key) or 0)
    out = []
    for data in buckets.values():
        item = data['row']
        item[name_key] = pick_dish_display(data['names'])
        item[count_key] = data['count']
        out.append(item)
    out.sort(key=lambda r: (-r[count_key], dish_label_key(r[name_key])))
    return out
