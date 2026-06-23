import json
import copy
import re
from html import unescape
from urllib.parse import unquote, urlparse

from django.urls import reverse
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


CKEDITOR_INLINE_PREFIX = 'reports/ckeditor5/'


def _ckeditor_relpath_from_url(url: str) -> str | None:
    if not url:
        return None
    raw = unescape(unquote(url.strip()))
    if raw.startswith('data:'):
        return None
    if raw.startswith(CKEDITOR_INLINE_PREFIX):
        return raw.split('?', 1)[0]
    parsed = urlparse(raw)
    path = unquote(parsed.path or raw)
    marker = f'/media/{CKEDITOR_INLINE_PREFIX}'
    idx = path.find(marker)
    if idx >= 0:
        return path[idx + len('/media/'):].split('?', 1)[0]
    if path.startswith(f'/{CKEDITOR_INLINE_PREFIX}'):
        return path.lstrip('/').split('?', 1)[0]
    return None


def strip_ckeditor_widget_markup(html: str) -> str:
    if not html:
        return ''
    cleaned = html
    for _ in range(6):
        updated = re.sub(
            r'<span[^>]*\bcke_widget_wrapper\b[^>]*>(.*?)</span>',
            r'\1',
            cleaned,
            flags=re.I | re.S,
        )
        if updated == cleaned:
            break
        cleaned = updated
    cleaned = re.sub(
        r'<span[^>]*\b(cke_image_resizer|cke_widget_drag_handler)\b[^>]*>.*?</span>',
        '',
        cleaned,
        flags=re.I | re.S,
    )
    return cleaned


def sanitize_document_html_for_storage(html: str) -> str:
    return strip_ckeditor_widget_markup(html or '')


def prepare_document_html_for_display(html: str, report, request) -> str:
    if not html:
        return ''
    from reports.daily_inline_images import inline_image_relpath_from_url

    cleaned = sanitize_document_html_for_storage(html)

    def repl_img(match):
        tag = match.group(0)
        src = _extract_html_attr(tag, 'src')
        saved = _extract_html_attr(tag, 'data-cke-saved-src')
        relpath = inline_image_relpath_from_url(saved or src or '')
        if not relpath:
            if saved and saved != src:
                tag = _replace_html_attr(tag, 'src', saved)
            return tag
        serve_url = request.build_absolute_uri(
            reverse('reports:document_image', kwargs={'report_pk': report.pk, 'relpath': relpath}),
        )
        tag = _replace_html_attr(tag, 'src', serve_url)
        tag = re.sub(r'\sdata-cke-saved-src=["\'][^"\']*["\']', '', tag, flags=re.I)
        return tag

    return re.sub(r'<img\b[^>]*>', repl_img, cleaned, flags=re.I)


def _extract_html_attr(tag: str, name: str) -> str:
    match = re.search(rf'\s{name}=["\']([^"\']*)["\']', tag, flags=re.I)
    return unescape(match.group(1)) if match else ''


def _replace_html_attr(tag: str, name: str, value: str) -> str:
    pattern = rf'\s{name}=["\'][^"\']*["\']'
    replacement = f' {name}="{value}"'
    if re.search(pattern, tag, flags=re.I):
        return re.sub(pattern, replacement, tag, count=1, flags=re.I)
    return tag[:-1] + replacement + '>'


def office_report_has_content(
    spreadsheet_json,
    document_html: str,
    *,
    attachment_count: int = 0,
    links_text: str = '',
) -> bool:
    data = normalize_spreadsheet_json(spreadsheet_json)
    if attachment_count > 0:
        return True
    if any(line.strip() for line in (links_text or '').splitlines()):
        return True
    return spreadsheet_has_content(data) or document_has_content(document_html)
