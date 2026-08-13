"""Xem trước file PDF / Word / Excel qua link chia sẻ NAS."""

from __future__ import annotations

import csv
import hashlib
import os
import tempfile
from datetime import date, datetime, time
from html import escape
from pathlib import Path
from urllib.parse import quote, urlencode

from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.urls import reverse

from tools.services import OFFICE_TO_PDF_EXTENSIONS, convert_office_path_to_pdf, office_preview_available

PDF_EXTENSIONS = frozenset({'.pdf'})
PREVIEWABLE_EXTENSIONS = PDF_EXTENSIONS | OFFICE_TO_PDF_EXTENSIONS
SPREADSHEET_HTML_EXTENSIONS = frozenset({'.xlsx', '.csv'})
WORD_HTML_EXTENSIONS = frozenset({'.docx'})
_SPREADSHEET_MAX_SHEETS = 8
_SPREADSHEET_MAX_ROWS = 200
_SPREADSHEET_MAX_COLS = 40


def preview_kind(file_name: str) -> str | None:
    ext = os.path.splitext((file_name or '').lower())[1]
    if ext in PDF_EXTENSIONS:
        return 'pdf'
    if ext in OFFICE_TO_PDF_EXTENSIONS:
        return 'office'
    return None


def can_preview_file(file_name: str) -> bool:
    return preview_kind(file_name) is not None


def can_embed_office_preview(file_name: str) -> bool:
    """Excel/CSV/Word (.docx) xem HTML ngay; .doc/.ods cần LibreOffice."""
    ext = os.path.splitext((file_name or '').lower())[1]
    if ext in SPREADSHEET_HTML_EXTENSIONS or ext in WORD_HTML_EXTENSIONS:
        return True
    if ext in OFFICE_TO_PDF_EXTENSIONS:
        return office_preview_available()
    return ext in PDF_EXTENSIONS


def _inline_content_disposition(filename: str) -> str:
    name = (filename or 'file').replace('\r', '').replace('\n', '').replace('"', '').replace('\\', '')
    ascii_fallback = ''.join(
        c if 32 <= ord(c) < 127 and c not in ';\\' else '_' for c in name
    ) or 'file'
    return f"inline; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(name)}"


def preview_url_for(rel_path: str, *, share_token: str = '') -> str:
    params = {'path': rel_path}
    if share_token:
        params['share'] = share_token
    return reverse('nas_storage:preview') + '?' + urlencode(params)


def share_preview_context(file_name: str, rel_path: str, *, share_token: str = '') -> dict | None:
    kind = preview_kind(file_name)
    if not kind:
        return None
    ctx = {
        'kind': kind,
        'preview_url': preview_url_for(rel_path, share_token=share_token),
        'file_name': file_name,
    }
    if kind == 'office':
        ctx['office_preview_ready'] = can_embed_office_preview(file_name)
    return ctx


def _office_pdf_cache_path(source: Path) -> Path:
    stat = source.stat()
    digest = hashlib.sha256(
        f'{source.resolve()}:{stat.st_mtime_ns}:{stat.st_size}'.encode()
    ).hexdigest()[:20]
    return Path(tempfile.gettempdir()) / 'nas-preview-cache' / f'{digest}.pdf'


def office_pdf_bytes(source: Path) -> bytes:
    cache = _office_pdf_cache_path(source)
    try:
        if cache.is_file() and cache.stat().st_mtime >= source.stat().st_mtime:
            return cache.read_bytes()
    except OSError:
        pass

    data, _ = convert_office_path_to_pdf(source)
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)
    except OSError:
        pass
    return data


def inline_pdf_response(path: Path, *, filename: str | None = None):
    from django.http import FileResponse

    name = filename or path.name
    response = FileResponse(path.open('rb'), content_type='application/pdf', as_attachment=False)
    response['Content-Disposition'] = _inline_content_disposition(name)
    response['Content-Length'] = path.stat().st_size
    return response


def inline_office_pdf_response(source: Path, *, display_name: str):
    try:
        data = office_pdf_bytes(source)
    except ValidationError:
        raise
    response = HttpResponse(data, content_type='application/pdf')
    pdf_name = os.path.splitext(display_name)[0] + '.pdf'
    response['Content-Disposition'] = _inline_content_disposition(pdf_name)
    response['Content-Length'] = len(data)
    return response


def docx_to_html(source: Path, display_name: str) -> str:
    import mammoth

    with source.open('rb') as fh:
        result = mammoth.convert_to_html(fh)
    body = (result.value or '').strip() or '<p>Tài liệu trống.</p>'
    return (
        '<!doctype html><meta charset="utf-8">'
        '<style>'
        'body{font-family:system-ui,Segoe UI,sans-serif;margin:0;padding:16px 20px;'
        'background:#fff;color:#0f172a;line-height:1.55}'
        'img{max-width:100%;height:auto}'
        'table{border-collapse:collapse;width:100%;margin:12px 0}'
        'td,th{border:1px solid #cbd5e1;padding:6px 8px}'
        '.note{color:#64748b;font-size:12px;margin:0 0 12px}'
        '</style>'
        f'<p class="note">{escape(display_name)}</p>'
        + body
    )


def inline_docx_html_response(source: Path, *, display_name: str) -> HttpResponse:
    try:
        html = docx_to_html(source, display_name)
    except Exception as exc:
        raise ValidationError('Không đọc được file Word.') from exc
    return HttpResponse(html, content_type='text/html; charset=utf-8')


def serve_preview_response(source: Path, display_name: str, *, ext: str | None = None):
    """PDF / Excel HTML / Word HTML — không 404 khi không xem được."""
    ext = (ext or source.suffix or os.path.splitext(display_name)[1]).lower()
    if ext == '.pdf':
        return inline_pdf_response(source, filename=display_name)
    if ext in SPREADSHEET_HTML_EXTENSIONS:
        try:
            return inline_spreadsheet_html_response(source, display_name=display_name)
        except ValidationError:
            return preview_unavailable_html('Không đọc được file Excel. Hãy tải xuống để mở.')
    if ext in WORD_HTML_EXTENSIONS:
        try:
            return inline_docx_html_response(source, display_name=display_name)
        except ValidationError:
            pass
        if office_preview_available():
            try:
                return inline_office_pdf_response(source, display_name=display_name)
            except ValidationError:
                pass
        return preview_unavailable_html('Không đọc được file Word. Hãy tải xuống để mở.')
    if ext in OFFICE_TO_PDF_EXTENSIONS:
        if office_preview_available():
            try:
                return inline_office_pdf_response(source, display_name=display_name)
            except ValidationError:
                pass
        return preview_unavailable_html(
            'Chưa xem trước được định dạng này trên trình duyệt. Hãy tải file về.'
        )
    return preview_unavailable_html('Không xem trước được file này.')


def preview_unavailable_html(message: str) -> HttpResponse:
    return HttpResponse(
        '<!doctype html><meta charset="utf-8">'
        '<body style="font-family:system-ui,sans-serif;padding:2rem;text-align:center;color:#64748b">'
        f'{escape(message)}'
        '</body>',
        content_type='text/html; charset=utf-8',
    )


def _cell_text(value) -> str:
    if value is None:
        return ''
    if isinstance(value, datetime):
        if value.hour or value.minute or value.second:
            return value.strftime('%d/%m/%Y %H:%M')
        return value.strftime('%d/%m/%Y')
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.strftime('%d/%m/%Y')
    if isinstance(value, time):
        return value.strftime('%H:%M')
    if isinstance(value, float):
        if value == int(value) and abs(value) < 1e15:
            return f'{int(value):,}'.replace(',', '.')
        return f'{value:g}'
    if isinstance(value, int) and not isinstance(value, bool):
        return f'{value:,}'.replace(',', '.')
    return str(value)


def _sheet_table_html(rows: list[list], *, title: str) -> str:
    if not rows:
        return f'<h2>{escape(title)}</h2><p class="note">Sheet trống.</p>'
    width = max(len(row) for row in rows)
    parts = [f'<h2>{escape(title)}</h2>', '<table>']
    for r_idx, row in enumerate(rows):
        parts.append('<tr>')
        tag = 'th' if r_idx == 0 else 'td'
        padded = list(row) + [''] * (width - len(row))
        for cell in padded:
            parts.append(f'<{tag}>{escape(_cell_text(cell))}</{tag}>')
        parts.append('</tr>')
    parts.append('</table>')
    return ''.join(parts)


def _xlsx_sheets(source: Path) -> list[tuple[str, list[list]]]:
    import openpyxl

    wb = openpyxl.load_workbook(source, read_only=True, data_only=False)
    try:
        sheets = []
        for ws in wb.worksheets[:_SPREADSHEET_MAX_SHEETS]:
            rows = []
            for row in ws.iter_rows(
                max_row=_SPREADSHEET_MAX_ROWS,
                max_col=_SPREADSHEET_MAX_COLS,
                values_only=True,
            ):
                rows.append(list(row))
            while rows and all(c is None or str(c).strip() == '' for c in rows[-1]):
                rows.pop()
            sheets.append((ws.title or 'Sheet', rows))
        return sheets
    finally:
        wb.close()


def _csv_sheets(source: Path) -> list[tuple[str, list[list]]]:
    raw = source.read_bytes()
    text = None
    for encoding in ('utf-8-sig', 'utf-8', 'cp1258', 'cp1252', 'latin-1'):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValidationError('Không đọc được file CSV.')
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=',;\t')
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(text.splitlines(), dialect)
    rows = []
    for i, row in enumerate(reader):
        if i >= _SPREADSHEET_MAX_ROWS:
            break
        rows.append(row[:_SPREADSHEET_MAX_COLS])
    while rows and all(not str(c).strip() for c in rows[-1]):
        rows.pop()
    return [(source.stem or 'CSV', rows)]


def spreadsheet_to_html(source: Path, display_name: str) -> str:
    ext = source.suffix.lower()
    if ext == '.xlsx':
        sheets = _xlsx_sheets(source)
    elif ext == '.csv':
        sheets = _csv_sheets(source)
    else:
        raise ValidationError('Định dạng bảng tính không xem nhanh được.')

    truncated = any(
        len(rows) >= _SPREADSHEET_MAX_ROWS for _, rows in sheets
    )
    bodies = [_sheet_table_html(rows, title=title) for title, rows in sheets]
    note = ''
    if truncated:
        note = (
            f'<p class="note">Chỉ hiện {_SPREADSHEET_MAX_ROWS} dòng × '
            f'{_SPREADSHEET_MAX_COLS} cột đầu — tải file để xem đủ.</p>'
        )
    return (
        '<!doctype html><meta charset="utf-8">'
        '<style>'
        'body{font-family:system-ui,Segoe UI,sans-serif;margin:0;background:#f1f5f9;color:#0f172a}'
        'h2{font-size:13px;margin:12px 12px 6px;color:#334155}'
        'table{border-collapse:collapse;margin:0 12px 16px;background:#fff;font-size:12px}'
        'th,td{border:1px solid #cbd5e1;padding:3px 8px;white-space:nowrap;'
        'max-width:280px;overflow:hidden;text-overflow:ellipsis}'
        'th{background:#e2e8f0;font-weight:600}'
        '.note{color:#64748b;font-size:11px;margin:8px 12px 16px}'
        '</style>'
        f'<p class="note">{escape(display_name)}</p>'
        + ''.join(bodies)
        + note
    )


def inline_spreadsheet_html_response(source: Path, *, display_name: str) -> HttpResponse:
    try:
        html = spreadsheet_to_html(source, display_name)
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError('Không đọc được file Excel.') from exc
    return HttpResponse(html, content_type='text/html; charset=utf-8')
