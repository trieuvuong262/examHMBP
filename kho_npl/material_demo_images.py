"""URL ảnh demo theo nhóm NPL — Unsplash (đã kiểm tra HTTP 200)."""

from __future__ import annotations

from urllib.parse import quote

# Ảnh Unsplash đã verify tải được (w=400 h=400)
_UNSPLASH = 'https://images.unsplash.com/{id}?w=400&h=400&fit=crop&q=80'
FABRIC = [
    _UNSPLASH.format(id='photo-1558171813-4c088753af8f'),
    _UNSPLASH.format(id='photo-1586105251261-72a756497a11'),
    _UNSPLASH.format(id='photo-1594938298603-c8148c4dae35'),
]
GENERAL = [
    _UNSPLASH.format(id='photo-1507679799987-c73779587ccf'),
    *FABRIC,
]

CATEGORY_DEMO_IMAGE_URLS: dict[str, list[str]] = {
    'vai': FABRIC,
    'vai-chinh': FABRIC,
    'vai-phoi': FABRIC,
    'nl-vai': FABRIC,
    'bo-vien': FABRIC,
    'bo-co-tay': FABRIC,
    'khoa-phu-kien': GENERAL,
    'day-khoa': GENERAL,
    'nhan-bao-bi': GENERAL,
    'tem-nhan': GENERAL,
    'bao-bi': GENERAL,
    'in-trang-tri': GENERAL,
    'decal': GENERAL,
    'chi-may-nhom': GENERAL,
    'chi-may': GENERAL,
    'pl-may': GENERAL,
    'pl-gapxep': FABRIC,
    'khac-nhom': GENERAL,
    'khac': GENERAL,
}

DEFAULT_DEMO_IMAGE_URLS = FABRIC


def picsum_fallback_url(material) -> str:
    seed = quote(f'npl-{material.pk}-{material.code}', safe='')
    return f'https://picsum.photos/seed/{seed}/400/400'


def demo_image_urls_for_material(material) -> list[str]:
    """Danh sách URL thử lần lượt (chính + dự phòng picsum)."""
    cat = material.category
    keys: list[str] = []
    if cat:
        keys.append(cat.code)
        if cat.parent_id:
            keys.append(cat.parent.code)
    for key in keys:
        urls = CATEGORY_DEMO_IMAGE_URLS.get(key)
        if urls:
            primary = urls[material.pk % len(urls)]
            return [primary, picsum_fallback_url(material)]
    primary = DEFAULT_DEMO_IMAGE_URLS[material.pk % len(DEFAULT_DEMO_IMAGE_URLS)]
    return [primary, picsum_fallback_url(material)]
