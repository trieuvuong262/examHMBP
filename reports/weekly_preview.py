"""Xem trước link / file báo cáo tuần."""

from __future__ import annotations

import os
import re
from urllib.parse import urlparse

PDF_EXTENSIONS = frozenset({'.pdf'})
IMAGE_EXTENSIONS = frozenset({'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'})


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
    for line in [part.strip() for part in (links_text or '').splitlines() if part.strip()]:
        parsed = urlparse(line)
        rows.append({
            'url': line,
            'domain': parsed.netloc.replace('www.', '') or line,
            'embed_url': embed_url_for_link(line),
        })
    return rows


def file_attachment_preview(att) -> dict:
    name = att.original_name or os.path.basename(att.file.name)
    lower = name.lower()
    ext = os.path.splitext(lower)[1]
    url = att.file_url
    if att.is_image or ext in IMAGE_EXTENSIONS:
        return {'type': 'image', 'url': url, 'name': name, 'pk': att.pk}
    if ext in PDF_EXTENSIONS:
        return {'type': 'pdf', 'url': url, 'name': name, 'pk': att.pk}
    return {
        'type': 'download',
        'url': url,
        'name': name,
        'ext': ext.lstrip('.').upper() or 'FILE',
        'pk': att.pk,
    }
