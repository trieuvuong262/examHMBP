"""Render danh sách hub Sản xuất (thay stub khi đã có model)."""

from __future__ import annotations

from django.shortcuts import render


def hub_list_page(
    request,
    *,
    perm_ctx: dict,
    title: str,
    subtitle: str,
    columns: list[dict],
    rows: list[dict],
    empty_hint: str = 'Chưa có dữ liệu. Chạy: python manage.py seed_san_xuat_demo',
    related_url_name: str | None = None,
    related_url: str | None = None,
):
    return render(request, 'san_xuat/hub_list.html', {
        **perm_ctx,
        'hub_title': title,
        'hub_subtitle': subtitle,
        'columns': columns,
        'rows': rows,
        'empty_hint': empty_hint,
        'related_url_name': related_url_name,
        'related_url': related_url,
    })


def _status_label(obj, field: str = 'status') -> str:
    val = getattr(obj, field, '')
    display = getattr(obj, f'get_{field}_display', None)
    if callable(display):
        return str(display())
    return str(val or '—')


def _rows_from_queryset(qs, fields: list[str]) -> list[dict]:
    """fields: tên thuộc tính model hoặc '_status' / '_str'."""
    out: list[dict] = []
    for obj in qs:
        cells = []
        for attr in fields:
            if attr == '_status':
                cells.append(_status_label(obj))
            elif attr == '_str':
                cells.append(str(obj))
            else:
                val = getattr(obj, attr, None)
                cells.append(val if val is not None and val != '' else '—')
        out.append({'cells': cells})
    return out
