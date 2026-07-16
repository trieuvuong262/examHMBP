"""URL names khi nhúng KiotViet catalog vào hub Sản xuất."""

from __future__ import annotations


def kv_url_name(request, key: str, default: str) -> str:
    urls = getattr(request, 'kv_embed_urls', None) or {}
    return urls.get(key) or default
