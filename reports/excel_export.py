"""Xuất báo cáo ngày ra Excel."""

from __future__ import annotations

import io
import re
from datetime import datetime

import pandas as pd
from django.http import HttpResponse
from django.utils.html import strip_tags

from reports.models import DailyWorkReport

from reports.production_shift_policy import PRODUCTION_SHIFT_ORDER, shift_display_label
from reports.office_content import normalize_spreadsheet_json, office_report_has_content
from reports.production_hourly import build_hourly_grid, build_productivity_report


def _safe_filename_part(text: str) -> str:
    """Chuỗi ASCII an toàn cho tên file tải về (tránh browser đặt tên download)."""
    from django.utils.text import slugify

    cleaned = slugify(text or '', allow_unicode=False).replace('-', '_')
    cleaned = re.sub(r'_+', '_', cleaned).strip('_')
    return cleaned[:50] or 'bao_cao'


def _content_disposition_attachment(filename: str) -> str:
    """Content-Disposition với tên file ASCII + UTF-8 (không để browser fallback 'download')."""
    from urllib.parse import quote

    name = (filename or 'bao_cao.xlsx').replace('"', '').replace('\\', '').replace('\n', '')
    ascii_fallback = ''.join(
        c if ord(c) < 128 and c not in ('"', '\\', ';', ' ') else '_'
        for c in name
    ).strip('_') or 'bao_cao.xlsx'
    if not ascii_fallback.lower().endswith('.xlsx') and name.lower().endswith('.xlsx'):
        ascii_fallback = f'{ascii_fallback}.xlsx'
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(name)}"


def _meta_rows(report: DailyWorkReport) -> list[list]:
    profile = getattr(report.employee, 'profile', None)
    employee_name = profile.full_name if profile and profile.full_name else report.employee.username
    department = profile.department.name if profile and profile.department_id else '—'
    status = report.get_status_display()
    if report.is_production_report:
        if report.hod_reviewed:
            reviewed = 'Đã duyệt'
        elif getattr(report, 'hod_rejected', False):
            reviewed = 'Không duyệt'
        else:
            reviewed = 'Chưa duyệt'
    else:
        reviewed = 'Có' if report.hod_reviewed else 'Không'
    submitted = report.submitted_at.strftime('%d/%m/%Y %H:%M') if report.submitted_at else '—'
    rows = [
        ['Nhân viên', employee_name],
        ['Bộ phận', department],
        ['Ngày báo cáo', report.report_date.strftime('%d/%m/%Y')],
    ]
    if report.is_production_report and report.shift:
        rows.append(['Ca làm', shift_display_label(report.shift)])
    rows.extend([
        ['Trạng thái', status],
        ['Duyệt (cấp trên)' if report.is_production_report else 'Đã xem (cấp trên)', reviewed],
        ['Thời gian nộp', submitted],
        ['Ghi chú cấp trên', report.hod_note or ''],
    ])
    return rows


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
    # Chỉ ASCII — trình duyệt không fallback thành "download"
    safe_prefix = re.sub(r'[^\w\-]+', '_', filename_prefix or 'bao_cao', flags=re.ASCII)
    safe_prefix = re.sub(r'_+', '_', safe_prefix).strip('_') or 'bao_cao'
    filename = f'{safe_prefix}_{stamp}.xlsx'
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = _content_disposition_attachment(filename)
    return response


def export_production_team_summary_xlsx(
    summary,
    *,
    date_from,
    date_to,
    shift_label: str,
    filename_kind: str = 'tong_hop',
) -> HttpResponse:
    """Xuất ma trận tổng hợp / thống kê SX (NV × ngày) ra Excel."""
    days = summary.get('days', [])
    day_headers = [f"{d['weekday']} {d['date'].strftime('%d/%m')}" for d in days]
    is_percent = summary.get('metric_is_percent', True)
    avg_label = summary.get('avg_column_label') or ('TB' if is_percent else 'Tổng')
    columns = [
        'STT',
        'Nhân viên',
        'Ca',
        'Bộ phận',
        *day_headers,
        f'{avg_label} chung' if is_percent else f'{avg_label} kỳ',
    ]

    team_label = 'TB team theo ngày' if is_percent else 'SL team theo ngày'
    team_row = ['', team_label, '', '']
    for d in days:
        avg = d.get('average')
        team_row.append(round(avg, 2) if avg is not None else '')
    overall = summary.get('overall_avg')
    team_row.append(round(overall, 2) if overall is not None else '')

    rows: list[list] = [team_row]
    sections = summary.get('shift_sections') or []
    if sections:
        for section in sections:
            if summary.get('split_by_shift') or len(sections) > 1:
                rows.append([
                    section.get('label') or '',
                    '',
                    '',
                    '',
                    *([''] * len(days)),
                    '',
                ])
            for group in section.get('groups', []):
                for member in group.get('members', []):
                    row = [
                        member['stt'],
                        member['name'],
                        member.get('shift_label') or section.get('label') or '',
                        member.get('division') or '',
                    ]
                    for cell in member['cells']:
                        val = cell.get('value', cell.get('efficiency_pct'))
                        row.append(round(val, 2) if val is not None else '')
                    avg = member.get('avg_value', member.get('avg_efficiency_pct'))
                    row.append(round(avg, 2) if avg is not None else '')
                    rows.append(row)
    else:
        for group in summary.get('groups', []):
            for member in group.get('members', []):
                row = [
                    member['stt'],
                    member['name'],
                    member.get('shift_label') or '',
                    member.get('division') or '',
                ]
                for cell in member['cells']:
                    val = cell.get('value', cell.get('efficiency_pct'))
                    row.append(round(val, 2) if val is not None else '')
                avg = member.get('avg_value', member.get('avg_efficiency_pct'))
                row.append(round(avg, 2) if avg is not None else '')
                rows.append(row)

    df = pd.DataFrame(rows, columns=columns)
    metric = summary.get('metric') or 'efficiency'
    metric_part = {
        'efficiency': 'hieu_suat',
        'time': 'hieu_suat_thoi_gian',
        'quantity': 'san_luong',
    }.get(metric, metric)
    date_span = f'{date_from.strftime("%Y%m%d")}_{date_to.strftime("%Y%m%d")}'
    shift_filter = (summary.get('shift_filter') or '').strip().upper()
    shift_part = shift_filter.lower() if shift_filter else 'tat_ca'
    if filename_kind == 'thong_ke':
        prefix = f'Thong_ke_BC_SX_{metric_part}_{shift_part}_{date_span}'
    else:
        prefix = f'Bao_cao_tong_hop_SX_{shift_part}_{date_span}'
    return _xlsx_response({'Tong_hop': df}, prefix)


def _employee_identity_cells(report: DailyWorkReport) -> dict:
    profile = getattr(report.employee, 'profile', None)
    employee_name = profile.full_name if profile and profile.full_name else report.employee.username
    employee_code = (profile.employee_code if profile and getattr(profile, 'employee_code', None) else '') or ''
    department = profile.department.name if profile and profile.department_id else ''
    division = ''
    if profile and getattr(profile, 'division_id', None) and getattr(profile, 'division', None):
        division = profile.division.name or ''
    if report.hod_reviewed:
        reviewed = 'Đã duyệt'
    elif getattr(report, 'hod_rejected', False):
        reviewed = 'Không duyệt'
    else:
        reviewed = 'Chưa duyệt'
    return {
        'Mã NS': employee_code,
        'Nhân viên': employee_name,
        'Phòng ban': department,
        'Bộ phận': division,
        'Ngày': report.report_date.strftime('%d/%m/%Y') if report.report_date else '',
        'Ca': shift_display_label(report.shift) if report.shift else '',
        'Trạng thái': report.get_status_display(),
        'Duyệt': reviewed,
    }


def _blank_if_none(value):
    return '' if value is None else value


def export_production_team_detail_xlsx(reports, *, date_from, date_to) -> HttpResponse | None:
    """Xuất mọi dòng công đoạn + khung giờ của tất cả BC SX trong khoảng ngày."""
    summary_columns = [
        'STT',
        'Mã NS',
        'Nhân viên',
        'Phòng ban',
        'Bộ phận',
        'Ngày',
        'Ca',
        'Trạng thái',
        'Duyệt',
        'Mã hàng',
        'Công đoạn',
        'Bắt đầu',
        'Kết thúc',
        'Số lượng',
        'Hư hỏng',
        'Định mức',
        'Thời gian công đoạn',
        'Hiệu suất %',
        'Bù hiệu suất %',
        'Hiệu suất hỗ trợ %',
        'Ghi chú',
        'Cập nhật',
    ]
    hourly_columns = [
        'STT',
        'Mã NS',
        'Nhân viên',
        'Phòng ban',
        'Bộ phận',
        'Ngày',
        'Ca',
        'Trạng thái',
        'Duyệt',
        'Mã hàng',
        'Công đoạn',
        'Khung giờ',
        'Số lượng',
        'Định mức',
        'Thời gian công đoạn',
        'Hiệu suất %',
        'Hư hỏng',
        'Ghi chú',
        'Lý do 0',
    ]
    shift_rank = {key: index for index, key in enumerate(PRODUCTION_SHIFT_ORDER)}
    sorted_reports = sorted(
        reports,
        key=lambda report: (
            report.report_date or date_from,
            (
                getattr(getattr(report.employee, 'profile', None), 'full_name', None)
                or report.employee.username
                or ''
            ),
            shift_rank.get(report.shift or '', 99),
            report.pk or 0,
        ),
    )
    summary_rows: list[dict] = []
    hourly_rows: list[dict] = []
    for report in sorted_reports:
        identity = _employee_identity_cells(report)
        productivity = build_productivity_report(report)
        for row in productivity.get('product_summaries') or []:
            summary_rows.append({
                **identity,
                'Mã hàng': row.get('product_code') or '',
                'Công đoạn': row.get('process_name') or '',
                'Bắt đầu': row.get('started_at_display') or '',
                'Kết thúc': row.get('ended_at_display') or '',
                'Số lượng': _blank_if_none(row.get('quantity')),
                'Hư hỏng': _blank_if_none(row.get('damaged_quantity')),
                'Định mức': _blank_if_none(row.get('norm_per_hour')),
                'Thời gian công đoạn': row.get('hours_display') or '',
                'Hiệu suất %': _blank_if_none(row.get('efficiency_pct')),
                'Bù hiệu suất %': _blank_if_none(row.get('efficiency_bonus_pct')),
                'Hiệu suất hỗ trợ %': _blank_if_none(row.get('efficiency_after_bonus_pct')),
                'Ghi chú': row.get('note') or '',
                'Cập nhật': row.get('updated_by_name') or '',
            })
        for row in productivity.get('hourly_rows') or []:
            hourly_rows.append({
                **identity,
                'Mã hàng': row.get('product_code') or '',
                'Công đoạn': row.get('process_name') or '',
                'Khung giờ': row.get('slot_label') or '',
                'Số lượng': _blank_if_none(row.get('quantity')),
                'Định mức': _blank_if_none(row.get('norm_per_hour')),
                'Thời gian công đoạn': row.get('hours_display') or '',
                'Hiệu suất %': _blank_if_none(row.get('efficiency_pct')),
                'Hư hỏng': _blank_if_none(row.get('damaged_quantity')),
                'Ghi chú': row.get('note') or '',
                'Lý do 0': row.get('zero_reason') if row.get('quantity') == 0 else '',
            })

    if not summary_rows and not hourly_rows:
        return None

    for index, row in enumerate(summary_rows, start=1):
        row['STT'] = index
    for index, row in enumerate(hourly_rows, start=1):
        row['STT'] = index

    sheets = {
        'Chi_tiet_cong_doan': pd.DataFrame(summary_rows, columns=summary_columns),
        'Chi_tiet_khung_gio': pd.DataFrame(hourly_rows, columns=hourly_columns),
    }
    date_span = f'{date_from.strftime("%Y%m%d")}_{date_to.strftime("%Y%m%d")}'
    return _xlsx_response(sheets, f'Chi_tiet_bao_cao_SX_{date_span}')


def can_export_daily_report(report: DailyWorkReport) -> bool:
    if report.is_production_report:
        return bool(report.shift_started_at)
    has_attachments = report.attachments.exists() if report.pk else False
    return office_report_has_content(
        report.spreadsheet_json,
        report.document_html or '',
        attachment_count=1 if has_attachments else 0,
    )


def export_daily_report_xlsx(report: DailyWorkReport) -> HttpResponse:
    profile = getattr(report.employee, 'profile', None)
    employee_name = profile.full_name if profile and profile.full_name else report.employee.username
    date_part = report.report_date.strftime('%Y%m%d')
    shift_part = ''
    if report.is_production_report and report.shift:
        shift_part = f'_{report.shift}'
    filename_prefix = f'Bao_cao_{_safe_filename_part(employee_name)}_{date_part}{shift_part}'

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
                'Định mức': row['norm_per_hour'],
                'Thời gian công đoạn': row['hours_display'],
                'Hiệu suất %': row['efficiency_pct'],
                'Cập nhật': row.get('updated_by_name') or '',
                'Bù hiệu suất %': row.get('efficiency_bonus_pct') or '',
                'Hiệu suất hỗ trợ %': row.get('efficiency_after_bonus_pct'),
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
                'Định mức': row['norm_per_hour'] or '',
                'Thời gian công đoạn': row['hours_display'],
                'Hiệu suất %': row['efficiency_pct'] if row['efficiency_pct'] is not None else '',
                'Hư hỏng': row.get('damaged_quantity') or '',
                'Ghi chú': row.get('note') or '',
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
