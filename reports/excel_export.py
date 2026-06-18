"""Xuất báo cáo ngày ra Excel."""

import io
import re
from datetime import datetime

import pandas as pd
from django.http import HttpResponse
from django.utils.html import strip_tags

from reports.models import DailyWorkReport
from reports.office_content import normalize_spreadsheet_json, office_report_has_content
from reports.production_hourly import build_hourly_grid, build_productivity_report


def _safe_filename_part(text: str) -> str:
    cleaned = re.sub(r'[^\w\-]+', '_', (text or '').strip())
    return cleaned[:40] or 'bao_cao'


def _meta_rows(report: DailyWorkReport) -> list[list]:
    profile = getattr(report.employee, 'profile', None)
    employee_name = profile.full_name if profile and profile.full_name else report.employee.username
    department = profile.department.name if profile and profile.department_id else '—'
    status = report.get_status_display()
    reviewed = 'Có' if report.hod_reviewed else 'Không'
    submitted = report.submitted_at.strftime('%d/%m/%Y %H:%M') if report.submitted_at else '—'
    return [
        ['Nhân viên', employee_name],
        ['Bộ phận', department],
        ['Ngày báo cáo', report.report_date.strftime('%d/%m/%Y')],
        ['Trạng thái', status],
        ['Đã xem (cấp trên)', reviewed],
        ['Thời gian nộp', submitted],
        ['Ghi chú cấp trên', report.hod_note or ''],
    ]


def _grid_cell_display(cell: dict) -> str:
    if cell.get('is_na'):
        return '—'
    if not cell.get('has_data'):
        return ''
    qty = cell.get('quantity') or 0
    if qty > 0:
        parts = [str(qty)]
        cumulative = cell.get('cumulative')
        if cumulative:
            parts.append(f'Σ{cumulative}')
        if cell.get('partial_hours'):
            parts.append(str(cell.get('display') or ''))
        return '\n'.join(part for part in parts if part)
    reason = (cell.get('zero_reason') or '').strip()
    return f'0\n{reason}' if reason else '0'


def _xlsx_response(sheets: dict[str, pd.DataFrame], filename_prefix: str) -> HttpResponse:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for sheet_name, df in sheets.items():
            use_header = sheet_name not in {'Thong_tin', 'Van_ban'}
            df.to_excel(writer, index=False, header=use_header, sheet_name=sheet_name[:31])
    stamp = datetime.now().strftime('%Y%m%d_%H%M')
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename={filename_prefix}_{stamp}.xlsx'
    return response


def can_export_daily_report(report: DailyWorkReport) -> bool:
    if report.is_production_report:
        return bool(report.shift_started_at)
    return office_report_has_content(report.spreadsheet_json, report.document_html or '')


def export_daily_report_xlsx(report: DailyWorkReport) -> HttpResponse:
    profile = getattr(report.employee, 'profile', None)
    employee_name = profile.full_name if profile and profile.full_name else report.employee.username
    date_part = report.report_date.strftime('%Y%m%d')
    filename_prefix = f'Bao_cao_{_safe_filename_part(employee_name)}_{date_part}'

    if report.is_production_report:
        return _export_production_report(report, filename_prefix)
    return _export_office_report(report, filename_prefix)


def _export_production_report(report: DailyWorkReport, filename_prefix: str) -> HttpResponse:
    productivity = build_productivity_report(report)
    hourly_grid = build_hourly_grid(report)

    sheets: dict[str, pd.DataFrame] = {
        'Thong_tin': pd.DataFrame(_meta_rows(report)),
    }

    if productivity.get('product_summaries'):
        summary_rows = []
        for index, row in enumerate(productivity['product_summaries'], start=1):
            summary_rows.append({
                'STT': index,
                'Mã hàng': row['product_code'],
                'Công đoạn': row['process_name'],
                'Số lượng': row['quantity'],
                'Định mức/H': row['norm_per_hour'],
                'Thời gian/H': row['hours_display'],
                'Hiệu suất %': row['efficiency_pct'],
            })
        sheets['Tong_hop'] = pd.DataFrame(summary_rows)

    if productivity.get('hourly_rows'):
        detail_rows = []
        for index, row in enumerate(productivity['hourly_rows'], start=1):
            detail_rows.append({
                'STT': index,
                'Mã hàng': row['product_code'],
                'Công đoạn': row['process_name'],
                'Khung giờ': row['slot_label'],
                'Số lượng': row['quantity'],
                'Định mức/H': row['norm_per_hour'] or '',
                'Thời gian/H': row['hours_display'],
                'Hiệu suất %': row['efficiency_pct'] if row['efficiency_pct'] is not None else '',
                'Lý do 0': row['zero_reason'] if row['quantity'] == 0 else '',
            })
        sheets['Nang_suat_chi_tiet'] = pd.DataFrame(detail_rows)

    if hourly_grid.get('rows'):
        slot_labels = [slot['label'] for slot in hourly_grid['slots']]
        grid_rows = []
        for index, row in enumerate(hourly_grid['rows'], start=1):
            item = {
                'STT': index,
                'Mã hàng': row['label_code'] or row['product_code'] or '—',
                'Công đoạn': row['label_process'] or row['process_name'] or 'Chưa gắn mã',
            }
            for slot_label, cell in zip(slot_labels, row['slots']):
                item[slot_label] = _grid_cell_display(cell)
            item['Tổng SL'] = row['total_quantity']
            grid_rows.append(item)
        sheets['San_luong'] = pd.DataFrame(grid_rows)

    if len(sheets) == 1:
        sheets['San_luong'] = pd.DataFrame([['Chưa có dữ liệu sản lượng']])

    return _xlsx_response(sheets, filename_prefix)


def _export_office_report(report: DailyWorkReport, filename_prefix: str) -> HttpResponse:
    sheet = normalize_spreadsheet_json(report.spreadsheet_json)
    columns = sheet['columns']
    rows = sheet['rows']

    table_df = pd.DataFrame(rows, columns=columns if columns else None)
    sheets: dict[str, pd.DataFrame] = {
        'Thong_tin': pd.DataFrame(_meta_rows(report)),
        'Bang': table_df,
    }

    doc_text = strip_tags(report.document_html or '').strip()
    if doc_text:
        sheets['Van_ban'] = pd.DataFrame([['Nội dung'], [doc_text]])

    return _xlsx_response(sheets, filename_prefix)
