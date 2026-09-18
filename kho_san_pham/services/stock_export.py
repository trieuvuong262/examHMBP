"""Xuất Excel tồn kho thành phẩm theo chi nhánh KiotViet."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
from django.http import HttpResponse

from kho_npl.services.excel_export import dataframe_to_xlsx_response


def _qty_cell(value) -> float:
    if value is None:
        return 0.0
    return float(Decimal(str(value)))


def stock_groups_to_dataframe(groups: list[dict], kv_columns: list[dict]) -> pd.DataFrame:
    """Một dòng / SKU (biến thể), cột tồn theo từng kho KV đang hiện trên trang."""
    branch_headers = [col['name'] for col in kv_columns]
    headers = [
        'Style',
        'SKU',
        'Tên',
        'Mã màu',
        'Tên màu',
        'Size',
        'Mã KiotViet',
        'Đang dùng',
        *branch_headers,
        'Tổng xưởng',
        'Tổng cửa hàng',
    ]
    rows: list[dict] = []
    for group in groups:
        style = group.get('style_code') or ''
        if style == '—':
            style = ''
        for variant in group.get('variants') or []:
            row = {
                'Style': style,
                'SKU': variant.get('code') or '',
                'Tên': group.get('name') or '',
                'Mã màu': variant.get('color_code') or '',
                'Tên màu': variant.get('color_label') or '',
                'Size': variant.get('size_label') or '',
                'Mã KiotViet': variant.get('kiotviet_code') or '',
                'Đang dùng': 'Có' if variant.get('is_active') else 'Không',
                'Tổng xưởng': _qty_cell(variant.get('qty_factory')),
                'Tổng cửa hàng': _qty_cell(variant.get('qty_store')),
            }
            for col, qty in variant.get('kv_branch_qtys_pairs') or []:
                row[col['name']] = _qty_cell(qty)
            for name in branch_headers:
                row.setdefault(name, 0.0)
            rows.append(row)
    if not rows:
        return pd.DataFrame(columns=headers)
    return pd.DataFrame(rows, columns=headers)


def export_stock_xlsx(groups: list[dict], kv_columns: list[dict]) -> HttpResponse:
    df = stock_groups_to_dataframe(groups, kv_columns)
    return dataframe_to_xlsx_response(df, 'ton_kho_san_pham', sheet_name='Ton_kho')
