import json
import copy

from django.utils.html import strip_tags

DEFAULT_SPREADSHEET = {
    'columns': ['', '', ''],
    'rows': [
        ['', '', ''],
        ['', '', ''],
        ['', '', ''],
        ['', '', ''],
        ['', '', ''],
    ],
}


def normalize_spreadsheet_json(raw) -> dict:
    if not raw:
        return copy.deepcopy(DEFAULT_SPREADSHEET)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return copy.deepcopy(DEFAULT_SPREADSHEET)
    if not isinstance(raw, dict):
        return copy.deepcopy(DEFAULT_SPREADSHEET)

    columns = [str(c) for c in raw.get('columns') or DEFAULT_SPREADSHEET['columns']]
    if not columns:
        columns = ['', '', '']
    rows_in = raw.get('rows') or []
    rows = []
    for row in rows_in:
        if not isinstance(row, list):
            continue
        padded = [str(cell) for cell in row]
        while len(padded) < len(columns):
            padded.append('')
        rows.append(padded[:len(columns)])
    if not rows:
        rows = [['' for _ in columns] for _ in range(5)]
    return {'columns': columns, 'rows': rows}


def spreadsheet_has_content(data: dict) -> bool:
    for row in data.get('rows', []):
        for cell in row:
            if str(cell).strip():
                return True
    return False


def document_has_content(html: str) -> bool:
    return len(strip_tags(html or '').strip()) >= 50


def office_report_has_content(spreadsheet_json, document_html: str, *, attachment_count: int = 0) -> bool:
    data = normalize_spreadsheet_json(spreadsheet_json)
    if attachment_count > 0:
        return True
    return spreadsheet_has_content(data) or document_has_content(document_html)
