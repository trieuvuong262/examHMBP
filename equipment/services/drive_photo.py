"""Tải ảnh thiết bị từ Google Drive (link công khai)."""

from __future__ import annotations

import re
from io import BytesIO

import requests
from django.core.files.base import ContentFile


def extract_drive_file_id(url: str) -> str | None:
    if not url:
        return None
    m = re.search(r'/d/([a-zA-Z0-9_-]+)', url)
    if m:
        return m.group(1)
    m = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', url)
    return m.group(1) if m else None


def first_drive_url(*values) -> str | None:
    for value in values:
        if not value:
            continue
        text = str(value).strip()
        for m in re.finditer(r'https?://[^\s\)\]]+', text):
            url = m.group(0).rstrip('.,;')
            if 'drive.google' in url or 'googleusercontent' in url:
                return url
    return None


def download_drive_image(file_id: str, *, timeout: int = 60) -> bytes | None:
    url = f'https://drive.google.com/uc?export=download&id={file_id}'
    try:
        resp = requests.get(url, timeout=timeout, allow_redirects=True)
    except requests.RequestException:
        return None
    if resp.status_code != 200 or len(resp.content) < 500:
        return None
    head = resp.content[:200].lower()
    if b'<html' in head or b'<!doctype' in head:
        return None
    return resp.content


def attach_photo_from_drive(device, *url_sources, filename_prefix: str = 'device') -> bool:
    """Gắn ảnh vào device.photo từ link Drive. Trả về True nếu thành công."""
    url = first_drive_url(*url_sources)
    if not url:
        return False
    file_id = extract_drive_file_id(url)
    if not file_id:
        return False
    data = download_drive_image(file_id)
    if not data:
        return False
    ext = 'jpg'
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        ext = 'png'
    elif data[:3] == b'GIF':
        ext = 'gif'
    elif data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        ext = 'webp'
    safe_code = (device.device_code or 'device').replace('/', '-')
    name = f'{filename_prefix}_{safe_code}.{ext}'
    device.photo.save(name, ContentFile(data), save=False)
    return True
