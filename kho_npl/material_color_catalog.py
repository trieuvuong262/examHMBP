"""Đồng bộ màu NPL và suy luận màu từ tên/mã NPL."""

from __future__ import annotations

import re
import unicodedata

from django.db.models import Q

from kho_npl.choices import ALL_MATERIAL_COLORS
from kho_npl.models import Material, MaterialColor
from kho_npl.services.material_colors import resolve_material_color

# (regex trên chuỗi đã chuẩn hóa, mã màu) — ưu tiên dài trước
_INFER_COLOR_RULES: tuple[tuple[str, str], ...] = (
    (r'xam[\s-]*melange|xám[\s-]*melange', 'xam-melange'),
    (r'xam[\s-]*chi|xám[\s-]*chì', 'xam-chi'),
    (r'xanh[\s-]*navy|\bnavy\b', 'navy'),
    (r'xanh[\s-]*ket|xanh[\s-]*két', 'xanh-ket'),
    (r'xanh[\s-]*den|xanh[\s-]*đen', 'xanh-den'),
    (r'xanh[\s-]*reu|rêu', 'xanh-reu'),
    (r'long[\s-]*cong|lông[\s-]*công', 'long-cong'),
    (r'co[\s-]*vit|cổ[\s-]*vịt', 'co-vit'),
    (r'ly[\s-]*dam|lý[\s-]*đậm', 'ly-dam'),
    (r'\bly\b|lý\b', 'ly'),
    (r'\bbien\b|biển', 'bien'),
    (r'\bngoc\b|ngọc', 'ngoc'),
    (r'đô\b', 'do-tim'),
    (r'vang[\s-]*cuc|vangcuc', 'vang-cuc'),
    (r'me[\s-]*mua|mè[\s-]*mưa', 'me-mua'),
    (r'xanh[\s-]*reu|rêu', 'xanh-reu'),
    (r'hong[\s-]*pastel', 'hong-pastel'),
    (r'trang[\s-]*gao|trắng[\s-]*gạo', 'vang-gao'),
    (r'trang[\s-]*mo|trắng[\s-]*mờ', 'trang-mo'),
    (r'nau[\s-]*carton', 'nau-carton'),
    (r'trong[\s-]*suot|trong\s*suốt|\btrong\b', 'trong'),
    (r'\bkraft\b', 'kraft'),
    (r'\bbich\b|bích', 'bich'),
    (r'do[\s-]*do|đỏ[\s-]*đô', 'do-do'),
    (r'do[\s-]*dam|đỏ[\s-]*đậm', 'do-dam'),
    (r'do[\s-]*tuoi|đỏ[\s-]*tươi', 'do-tuoi'),
    (r'xam[\s-]*dam|xám[\s-]*đậm', 'xam-dam'),
    (r'xam[\s-]*nhat|xám[\s-]*nhạt', 'xam-nhat'),
    (r'xanh[\s-]*duong[\s-]*dam', 'xanh-duong-dam'),
    (r'xanh[\s-]*duong', 'xanh-duong'),
    (r'xanh[\s-]*la[\s-]*dam', 'xanh-la-dam'),
    (r'xanh[\s-]*la', 'xanh-la'),
    (r'vang[\s-]*dong|đồng\b', 'vang-dong'),
    (r'vang[\s-]*sen', 'vang-sen'),
    (r'vang[\s-]*chanh', 'vang-chanh'),
    (r'hong[\s-]*dam', 'hong-dam'),
    (r'hong[\s-]*nhat', 'hong-nhat'),
    (r'hong[\s-]*san[\s-]*ho', 'hong-san-ho'),
    (r'cam[\s-]*dam', 'cam-dam'),
    (r'cam[\s-]*nhat', 'cam-nhat'),
    (r'tim[\s-]*dam', 'tim-dam'),
    (r'tim[\s-]*nhat', 'tim-nhat'),
    (r'nau[\s-]*dam', 'nau-dam'),
    (r'den[\s-]*tuyen|đen[\s-]*tuyền', 'den-tuyen'),
    (r'\bden\b|đen', 'den'),
    (r'\btrang\b|trắng', 'trang'),
    (r'\bxam\b|xám', 'xam'),
    (r'\bdo\b|đỏ', 'do'),
    (r'\bhong\b|hồng', 'hong'),
    (r'\bcam\b', 'cam'),
    (r'\bvang\b|vàng', 'vang'),
    (r'\bkem\b', 'kem'),
    (r'\bbe\b', 'be'),
    (r'\bnau\b|nâu', 'nau'),
    (r'\btim\b|tím', 'tim'),
    (r'\bbac\b|bạc', 'bac'),
    (r'\bda\b', 'da'),
    (r'\bghi\b', 'ghi'),
)


def _normalize_text(text: str) -> str:
    text = unicodedata.normalize('NFD', (text or '').lower())
    return ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn')


def ensure_material_colors() -> int:
    """Tạo/cập nhật toàn bộ màu chuẩn + màu bổ sung. Trả về số màu đã xử lý."""
    count = 0
    for code, name, hex_code, sort_order in ALL_MATERIAL_COLORS:
        obj, _ = MaterialColor.objects.get_or_create(
            code=code,
            defaults={
                'name': name,
                'hex_code': hex_code,
                'sort_order': sort_order,
                'is_active': True,
            },
        )
        updated = False
        if obj.name != name:
            obj.name = name
            updated = True
        if obj.hex_code.upper() != hex_code.upper():
            obj.hex_code = hex_code
            updated = True
        if obj.sort_order != sort_order:
            obj.sort_order = sort_order
            updated = True
        if not obj.is_active:
            obj.is_active = True
            updated = True
        if updated:
            obj.save()
        count += 1
    return count


def _color_by_code(code: str) -> MaterialColor | None:
    return MaterialColor.objects.filter(code=code, is_active=True).first()


def _suffix_after_dash(name: str) -> str | None:
    for sep in ('—', ' – ', ' - ', '-'):
        if sep in name:
            tail = name.rsplit(sep, 1)[-1].strip()
            tail = re.sub(r'\s*\([^)]*\)\s*', '', tail).strip()
            if tail:
                return tail
    return None


def _suffix_color_candidates(name: str) -> list[str]:
    tail = _suffix_after_dash(name)
    if not tail:
        return []
    parts = [tail]
    first = tail.split()[0] if tail.split() else ''
    if first and first not in parts:
        parts.append(first)
    return parts


def infer_material_color(material: Material) -> MaterialColor | None:
    """Suy luận màu từ tên/mã NPL (không ghi DB)."""
    for candidate in _suffix_color_candidates(material.name):
        found = resolve_material_color(candidate)
        if found:
            return found

    haystack = f'{material.name} {material.code}'.lower()
    haystack_norm = _normalize_text(haystack)
    for pattern, code in _INFER_COLOR_RULES:
        if re.search(pattern, haystack, flags=re.IGNORECASE) or re.search(
            pattern, haystack_norm, flags=re.IGNORECASE
        ):
            found = _color_by_code(code)
            if found:
                return found
    return None


def backfill_material_colors(*, only_missing: bool = True) -> tuple[int, int]:
    """
    Gán màu cho NPL. Trả về (đã gán, không suy luận được).
    """
    # only(...) tránh SELECT cột mới (vd. variant_group) khi migration cũ chạy.
    qs = Material.objects.only('id', 'code', 'name', 'color_id').select_related('color')
    if only_missing:
        qs = qs.filter(color__isnull=True)

    assigned = 0
    skipped = 0
    for material in qs.iterator():
        color = infer_material_color(material)
        if not color:
            skipped += 1
            continue
        material.color = color
        material.save(update_fields=['color'])
        assigned += 1
    return assigned, skipped
