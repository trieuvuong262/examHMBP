"""Xem trước link / file báo cáo tuần & VP."""

from __future__ import annotations

import os
import re
from urllib.parse import urlparse

from django.urls import reverse

from nas_storage.file_preview import can_embed_office_preview
from reports.link_utils import extract_urls_from_text, link_line_note, parse_link_lines
from tools.services import OFFICE_TO_PDF_EXTENSIONS

PDF_EXTENSIONS = frozenset({'.pdf'})
IMAGE_EXTENSIONS = frozenset({'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'})
PREVIEWABLE_FILE_EXTENSIONS = PDF_EXTENSIONS | OFFICE_TO_PDF_EXTENSIONS


def embed_url_for_link(url: str) -> str | None:
    """URL nhúng iframe cho Drive, Docs, YouTube — None nếu chỉ mở tab mới."""
    url = (url or '').strip()
    if not url:
        return None

    m = re.search(r'drive\.google\.com/file/d/([^/]+)', url, re.I)
    if m:
        return f'https://drive.google.com/file/d/{m.group(1)}/preview'

    for kind in ('document', 'spreadsheets', 'presentation'):
        m = re.search(rf'docs\.google\.com/{kind}/d/([^/]+)', url, re.I)
        if m:
            return f'https://docs.google.com/{kind}/d/{m.group(1)}/preview'

    m = re.search(r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([\w-]+)', url, re.I)
    if m:
        return f'https://www.youtube.com/embed/{m.group(1)}'

    return None


def link_preview_rows(links_text: str) -> list[dict]:
    rows = []
    notes_by_url: dict[str, str] = {}
    for line in [part.strip() for part in (links_text or '').splitlines() if part.strip()]:
        line_urls = extract_urls_from_text(line) or parse_link_lines(line)
        for url in line_urls:
            note = link_line_note(line, url)
            if note and url not in notes_by_url:
                notes_by_url[url] = note

    for url in parse_link_lines(links_text):
        parsed = urlparse(url)
        rows.append({
            'url': url,
            'note': notes_by_url.get(url, ''),
            'label': parsed.netloc.replace('www.', '') or url,
            'domain': parsed.netloc.replace('www.', '') or url,
            'embed_url': embed_url_for_link(url),
        })
    return rows


def _preview_route_for(att) -> str:
    class_name = att.__class__.__name__
    if class_name == 'WeeklyWorkReportAttachment':
        return 'reports:weekly_attachment_preview'
    if class_name == 'ReportCommentAttachment':
        return 'reports:comment_attachment_preview'
    return 'reports:daily_attachment_preview'


def attachment_content_disposition(filename: str) -> str:
    """Content-Disposition giữ đúng tên file (kể cả tiếng Việt)."""
    from urllib.parse import quote

    name = (filename or 'download').replace('"', '').replace('\\', '')
    ascii_fallback = ''.join(c if ord(c) < 128 and c not in ('"', '\\') else '_' for c in name) or 'download'
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(name)}"


def attachment_download_url(att) -> str:
    url = att.file_url
    if not url:
        return ''
    return f'{url}?download=1'


def file_attachment_preview(att) -> dict:
    name = att.original_name or os.path.basename(att.file.name)
    lower = name.lower()
    ext = os.path.splitext(lower)[1]
    url = att.file_url
    download_url = attachment_download_url(att)
    if att.is_image or ext in IMAGE_EXTENSIONS:
        return {
            'type': 'image',
            'url': url,
            'download_url': download_url,
            'preview_url': url,
            'name': name,
            'pk': att.pk,
        }
    if ext in PDF_EXTENSIONS:
        return {
            'type': 'pdf',
            'url': url,
            'download_url': download_url,
            'preview_url': url,
            'name': name,
            'pk': att.pk,
        }
    if ext in OFFICE_TO_PDF_EXTENSIONS:
        ready = can_embed_office_preview(name)
        preview_url = reverse(_preview_route_for(att), kwargs={'pk': att.pk}) if ready else ''
        return {
            'type': 'office',
            'url': url,
            'download_url': download_url,
            'preview_url': preview_url,
            'office_preview_ready': ready,
            'name': name,
            'ext': ext.lstrip('.').upper() or 'FILE',
            'pk': att.pk,
        }
    return {
        'type': 'download',
        'url': url,
        'download_url': download_url,
        'preview_url': '',
        'name': name,
        'ext': ext.lstrip('.').upper() or 'FILE',
        'pk': att.pk,
    }


def file_preview_is_embeddable(item: dict) -> bool:
    if item.get('type') == 'pdf':
        return bool(item.get('preview_url'))
    if item.get('type') == 'office':
        return bool(item.get('office_preview_ready') and item.get('preview_url'))
    return False
