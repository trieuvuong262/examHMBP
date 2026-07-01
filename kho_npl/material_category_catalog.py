"""Đồng bộ nhóm 2 cấp và gán lại NPL từ nhóm cũ (cấp 1 phẳng)."""

from __future__ import annotations

import re
import unicodedata

from kho_npl.category_tree import ensure_material_category_tree
from kho_npl.models import Material, MaterialCategory

# Nhóm cấp 1 cũ (không có con) → nhóm cấp 2 mặc định khi không suy luận được
LEGACY_ROOT_DEFAULT_LEAF: dict[str, str] = {
    'nl-vai': 'vai-chinh',
    'pl-may': 'day-khoa',
    'pl-gapxep': 'bao-bi',
}

# Nhóm cấp 1 cũ cần ẩn sau khi chuyển hết NPL sang cấp 2
LEGACY_ROOT_CODES = frozenset(LEGACY_ROOT_DEFAULT_LEAF.keys())

# (regex trên tên/mã, mã nhóm cấp 2)
_INFER_LEAF_RULES: tuple[tuple[str, str], ...] = (
    (r'bo[\s-]*(co|tay|gau|gấu|cổ)|\brib\b', 'bo-co-tay'),
    (r'vai[\s-]*(lot|lót|phoi|phối)|\blot\b|\blót\b', 'vai-phoi'),
    (r'\bchi\b|chỉ[\s-]*may|overlock', 'chi-may'),
    (r'decal|heat[\s-]*transfer|in[\s-]*ep', 'decal'),
    (r'tem[\s-]*nhan|tem[\s-]*nhãn|tag[\s-]*treo|nhãn|nhan[\s-]*giat|wash[\s-]*care|sticker[\s-]*size', 'tem-nhan'),
    (r'\bbich\b|bịch|tui[\s-]*opp|túi[\s-]*opp|\bopp\b|\bhd\b|tui[\s-]*pe|túi[\s-]*pe|thung[\s-]*carton|thùng', 'bao-bi'),
    (r'day[\s-]*keo|dây[\s-]*kéo|dây[\s-]*rut|dây[\s-]*rút|\bzip\b|nut[\s-]*nhua|nút[\s-]*nhựa|\bnut\b|\bnút\b|khoen|khuy[\s-]*cuc', 'day-khoa'),
    (r'day[\s-]*co|dây[\s-]*cổ|day[\s-]*xo|dây[\s-]*xỏ|day[\s-]*polo|dây[\s-]*polo|day[\s-]*nilon|dây[\s-]*nilon', 'vai-phoi'),
    (r'vai[\s-]|bột|\bbot\b|cotton|polyester|spandex|french[\s-]*terry|pique|mesh|interlock|fleece|terry|linen|4[\s-]*chieu|4[\s-]*chiều|casau|cá[\s-]*sấu|\bsieu\b|siêu|\bcr3\b|\bcsm1\b|\bcs2d\b|\bmk11\b|satin|thun|vải', 'vai-chinh'),
    (r'keo[\s-]*dan|giấy|giay|hut[\s-]*am|hút[\s-]*ẩm|nuoc[\s-]*ac|nước[\s-]*ac|dan[\s-]*ty|kim[\s-]*may|kéo[\s-]*bấm', 'khac'),
)


def _normalize_text(text: str) -> str:
    text = unicodedata.normalize('NFD', (text or '').lower())
    return ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn')


def _leaf_by_code(code: str) -> MaterialCategory | None:
    return MaterialCategory.objects.filter(code=code, is_active=True, parent__isnull=False).first()


def infer_material_leaf_category(material: Material) -> MaterialCategory | None:
    """Suy luận nhóm cấp 2 từ tên/mã và nhóm hiện tại."""
    cat = material.category
    if cat and cat.parent_id:
        return cat

    haystack = f'{material.name} {material.code}'.lower()
    haystack_norm = _normalize_text(haystack)
    for pattern, leaf_code in _INFER_LEAF_RULES:
        if re.search(pattern, haystack, flags=re.IGNORECASE) or re.search(
            pattern, haystack_norm, flags=re.IGNORECASE
        ):
            leaf = _leaf_by_code(leaf_code)
            if leaf:
                return leaf

    if cat and cat.code in LEGACY_ROOT_DEFAULT_LEAF:
        return _leaf_by_code(LEGACY_ROOT_DEFAULT_LEAF[cat.code])

    if cat and cat.parent_id is None and not cat.children.exists():
        # Nhóm cấp 1 không có con nhưng trùng mã con chuẩn (vd. code vai-chinh gán nhầm cấp 1)
        leaf = _leaf_by_code(cat.code)
        if leaf:
            return leaf

    return None


def backfill_material_categories(*, only_without_parent: bool = True) -> tuple[int, int]:
    """
    Gán NPL vào nhóm cấp 2.
    Trả về (đã gán, bỏ qua).
    """
    qs = Material.objects.select_related('category', 'category__parent')
    if only_without_parent:
        qs = qs.filter(category__parent__isnull=True)

    assigned = 0
    skipped = 0
    for material in qs.iterator():
        leaf = infer_material_leaf_category(material)
        if not leaf or material.category_id == leaf.pk:
            if material.category and material.category.parent_id is None:
                skipped += 1
            continue
        material.category = leaf
        material.save(update_fields=['category'])
        assigned += 1
    return assigned, skipped


def deactivate_empty_legacy_roots() -> int:
    """Ẩn nhóm cấp 1 cũ không còn NPL."""
    deactivated = 0
    for code in LEGACY_ROOT_CODES:
        root = MaterialCategory.objects.filter(code=code, parent__isnull=True).first()
        if not root or not root.is_active:
            continue
        if Material.objects.filter(category=root).exists():
            continue
        root.is_active = False
        root.save(update_fields=['is_active'])
        deactivated += 1
    return deactivated


def sync_material_category_catalog(*, backfill: bool = True) -> dict[str, int]:
    """Đồng bộ cây nhóm + gán NPL + ẩn nhóm cũ."""
    ensure_material_category_tree()
    roots = MaterialCategory.objects.filter(is_active=True, parent__isnull=True).count()
    leaves = MaterialCategory.objects.filter(is_active=True, parent__isnull=False).count()

    assigned = skipped = deactivated = 0
    if backfill:
        assigned, skipped = backfill_material_categories(only_without_parent=True)
        deactivated = deactivate_empty_legacy_roots()

    with_parent = Material.objects.filter(is_active=True, category__parent__isnull=False).count()
    active_total = Material.objects.filter(is_active=True).count()
    return {
        'roots': roots,
        'leaves': leaves,
        'assigned': assigned,
        'skipped': skipped,
        'deactivated_legacy': deactivated,
        'materials_with_parent': with_parent,
        'materials_active': active_total,
    }
