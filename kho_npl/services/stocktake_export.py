import pandas as pd

from kho_npl.choices import STOCKTAKE_STATUS_LABELS
from kho_npl.services.excel_export import dataframes_to_xlsx_response, dataframe_to_xlsx_response


def _user_label(user) -> str:
    if not user:
        return ''
    return user.get_full_name() or user.username or ''


def stocktake_list_export_response(qs):
    rows = []
    for st in qs.select_related('created_by', 'location').order_by('location__code', '-stocktake_date', '-pk'):
        rows.append({
            'Mã kỳ': st.number,
            'Tên kỳ': st.name,
            'Kho': st.location.code,
            'Tên kho': st.location.name or '',
            'Ngày kiểm kê': st.stocktake_date.strftime('%d/%m/%Y'),
            'Trạng thái': STOCKTAKE_STATUS_LABELS.get(st.status, st.status),
            'Người tạo': _user_label(st.created_by),
            'Ghi chú': st.notes or '',
        })
    df = pd.DataFrame(rows)
    return dataframe_to_xlsx_response(df, 'Danh_sach_kiem_ke', 'Kiem_ke')


def stocktake_detail_export_response(stocktake):
    header_df = pd.DataFrame([{
        'Mã kỳ': stocktake.number,
        'Tên kỳ': stocktake.name,
        'Kho': stocktake.location.code,
        'Tên kho': stocktake.location.name or '',
        'Ngày kiểm kê': stocktake.stocktake_date.strftime('%d/%m/%Y'),
        'Trạng thái': STOCKTAKE_STATUS_LABELS.get(stocktake.status, stocktake.status),
        'Người tạo': _user_label(stocktake.created_by),
        'Ghi chú': stocktake.notes or '',
    }])
    line_rows = []
    for line in stocktake.lines.select_related('material__unit').order_by('material__code'):
        actual = line.actual_qty
        variance = line.variance
        line_rows.append({
            'Mã NPL': line.material.code,
            'Tên NPL': line.material.name,
            'ĐVT': line.material.unit.name if line.material.unit_id else '',
            'Tồn HT': float(line.system_qty),
            'Tồn TT': float(actual) if actual is not None else None,
            'Chênh': float(variance) if variance is not None else None,
            'Ghi chú dòng': line.notes or '',
        })
    lines_df = pd.DataFrame(line_rows)
    return dataframes_to_xlsx_response(
        {'Phieu': header_df, 'Chi_tiet': lines_df},
        f'Kiem_ke_{stocktake.number}',
    )
