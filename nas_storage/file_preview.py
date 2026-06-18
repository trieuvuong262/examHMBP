"""Xem trước file PDF / Word / Excel qua link chia sẻ NAS."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from urllib.parse import urlencode

from django.core.exceptions import ValidationError
from django.urls import reverse

from tools.services import OFFICE_TO_PDF_EXTENSIONS, convert_office_path_to_pdf, office_preview_available

PDF_EXTENSIONS = frozenset({'.pdf'})
PREVIEWABLE_EXTENSIONS = PDF_EXTENSIONS | OFFICE_TO_PDF_EXTENSIONS


def preview_kind(file_name: str) -> str | None:
    ext = os.path.splitext((file_name or '').lower())[1]
    if ext in PDF_EXTENSIONS:
        return 'pdf'
    if ext in OFFICE_TO_PDF_EXTENSIONS:
        return 'office'
    return None


def can_preview_file(file_name: str) -> bool:
    return preview_kind(file_name) is not None


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
        ctx['office_preview_ready'] = office_preview_available()
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
    response['Content-Disposition'] = f'inline; filename="{name}"'
    response['Content-Length'] = path.stat().st_size
    return response


def inline_office_pdf_response(source: Path, *, display_name: str):
    from django.http import HttpResponse

    try:
        data = office_pdf_bytes(source)
    except ValidationError:
        raise
    response = HttpResponse(data, content_type='application/pdf')
    pdf_name = os.path.splitext(display_name)[0] + '.pdf'
    response['Content-Disposition'] = f'inline; filename="{pdf_name}"'
    response['Content-Length'] = len(data)
    return response
