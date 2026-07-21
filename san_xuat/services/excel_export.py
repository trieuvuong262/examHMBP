"""Xuất Excel dùng chung cho danh sách Sản xuất."""

import io
from datetime import datetime

import pandas as pd
from django.http import HttpResponse


def dataframe_to_xlsx_response(
    df: pd.DataFrame,
    filename_prefix: str,
    sheet_name: str = 'Danh_sach',
) -> HttpResponse:
    return dataframes_to_xlsx_response({sheet_name: df}, filename_prefix)


def dataframes_to_xlsx_response(
    sheets: dict[str, pd.DataFrame],
    filename_prefix: str,
) -> HttpResponse:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for sheet_name, df in sheets.items():
            safe = (sheet_name or 'Sheet')[:31]
            (df if df is not None else pd.DataFrame()).to_excel(
                writer, index=False, sheet_name=safe,
            )
    stamp = datetime.now().strftime('%Y%m%d_%H%M')
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename={filename_prefix}_{stamp}.xlsx'
    return response
