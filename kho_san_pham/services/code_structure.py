"""Sinh Style / resolve map KV → loại mã."""

from __future__ import annotations

from django.db.models import Max
from django.utils import timezone

from kho_san_pham.choices import (
    DEFAULT_BRAND,
    DEFAULT_STYLE_GROUP,
    KV_MAP_MATCH_CONTAINS,
    KV_MAP_MATCH_EXACT,
    STYLE_SOURCE_KIOTVIET,
    STYLE_SOURCE_MANUAL,
)
from kho_san_pham.catalog_models import ProductStyle, ProductType, ProductTypeKvMap


class CodeStructureError(Exception):
    pass


def normalize_type_code(value: str) -> str:
    return (value or '').strip().upper()


def type_code_has_group(type_code: str) -> bool:
    """Loại đã gắn nhóm trong mã (SET-SC, ACC-BALO) — không chèn nhóm mặc định."""
    return '-' in normalize_type_code(type_code)


def compose_kv_style_suffix(*, type_code: str, root_kiotviet_code: str, group: str = DEFAULT_STYLE_GROUP) -> str:
    """Hậu tố Style KV: ``00-SP007105`` hoặc ``SP002771`` nếu loại đã có nhóm."""
    root = (root_kiotviet_code or '').strip().upper()
    if not root:
        raise CodeStructureError('Thiếu mã KV gốc.')
    if type_code_has_group(type_code):
        return root
    grp = (group or DEFAULT_STYLE_GROUP).strip().upper() or DEFAULT_STYLE_GROUP
    return f'{grp}-{root}'


def compose_style_code(*, brand: str, type_code: str, suffix: str) -> str:
    brand = (brand or DEFAULT_BRAND).strip().upper() or DEFAULT_BRAND
    type_code = normalize_type_code(type_code)
    suffix = (suffix or '').strip().upper()
    if not type_code or not suffix:
        raise CodeStructureError('Thiếu loại hoặc hậu tố Style.')
    code = f'{brand}-{type_code}-{suffix}'
    if len(code) > 80:
        raise CodeStructureError('Mã Style vượt quá 80 ký tự.')
    return code


def next_manual_sequence(*, type_code: str, year: int | None = None, brand: str = DEFAULT_BRAND) -> int:
    year = int(year or timezone.now().year)
    type_code = normalize_type_code(type_code)
    brand = (brand or DEFAULT_BRAND).strip().upper() or DEFAULT_BRAND
    qs = ProductStyle.objects.filter(
        brand__iexact=brand,
        product_type__code__iexact=type_code,
        year=year,
        source=STYLE_SOURCE_MANUAL,
    )
    current = qs.aggregate(m=Max('sequence')).get('m') or 0
    return int(current) + 1


def create_manual_style(
    *,
    product_type: ProductType,
    name: str = '',
    brand: str = DEFAULT_BRAND,
    year: int | None = None,
    sequence: int | None = None,
    user=None,
) -> ProductStyle:
    year = int(year or timezone.now().year)
    yy = year % 100
    seq = int(sequence) if sequence is not None else next_manual_sequence(
        type_code=product_type.code, year=year, brand=brand,
    )
    if seq < 1 or seq > 9999:
        raise CodeStructureError('STT Style phải từ 1 đến 9999.')
    # Cùng quy tắc nhóm với Style KV: TEE → JP-TEE-00-260001; SET-SC → JP-SET-SC-260001
    seq_part = f'{yy:02d}{seq:04d}'
    if type_code_has_group(product_type.code):
        suffix = seq_part
    else:
        suffix = f'{DEFAULT_STYLE_GROUP}-{seq_part}'
    code = compose_style_code(brand=brand, type_code=product_type.code, suffix=suffix)
    if ProductStyle.objects.filter(code__iexact=code).exists():
        raise CodeStructureError(f'Style {code} đã tồn tại.')
    return ProductStyle.objects.create(
        code=code,
        product_type=product_type,
        name=(name or '').strip()[:500],
        brand=(brand or DEFAULT_BRAND).strip().upper() or DEFAULT_BRAND,
        year=year,
        sequence=seq,
        source=STYLE_SOURCE_MANUAL,
        is_active=True,
        created_by=user,
    )


def get_or_create_kv_style(
    *,
    product_type: ProductType,
    root_kiotviet_code: str,
    name: str = '',
    brand: str = DEFAULT_BRAND,
    group: str = DEFAULT_STYLE_GROUP,
) -> tuple[ProductStyle, bool]:
    root = (root_kiotviet_code or '').strip()
    if not root:
        raise CodeStructureError('Thiếu mã KV gốc.')
    suffix = compose_kv_style_suffix(
        type_code=product_type.code,
        root_kiotviet_code=root,
        group=group,
    )
    code = compose_style_code(brand=brand, type_code=product_type.code, suffix=suffix)
    existing = ProductStyle.objects.filter(code__iexact=code).first()
    if existing:
        fields: list[str] = []
        if name and not existing.name:
            existing.name = name.strip()[:500]
            fields.append('name')
        if root and existing.root_kiotviet_code != root:
            existing.root_kiotviet_code = root
            fields.append('root_kiotviet_code')
        if not existing.is_active:
            existing.is_active = True
            fields.append('is_active')
        if fields:
            existing.save(update_fields=fields + ['updated_at'])
        return existing, False
    # Style cũ thiếu nhóm (JP-JKT-SP007105) → nâng lên mã chuẩn nếu còn
    legacy = None
    if not type_code_has_group(product_type.code):
        legacy_code = compose_style_code(brand=brand, type_code=product_type.code, suffix=root)
        legacy = ProductStyle.objects.filter(code__iexact=legacy_code).first()
    if legacy:
        if ProductStyle.objects.filter(code__iexact=code).exclude(pk=legacy.pk).exists():
            legacy.is_active = False
            legacy.save(update_fields=['is_active', 'updated_at'])
            existing = ProductStyle.objects.filter(code__iexact=code).first()
            return existing, False
        legacy.code = code
        if name and not legacy.name:
            legacy.name = name.strip()[:500]
        if root:
            legacy.root_kiotviet_code = root
        legacy.is_active = True
        legacy.save()
        return legacy, False
    style = ProductStyle.objects.create(
        code=code,
        product_type=product_type,
        name=(name or '').strip()[:500],
        brand=(brand or DEFAULT_BRAND).strip().upper() or DEFAULT_BRAND,
        root_kiotviet_code=root,
        source=STYLE_SOURCE_KIOTVIET,
        is_active=True,
    )
    return style, True


def resolve_type_for_category(category_name: str) -> ProductType | None:
    """Ưu tiên exact, rồi contains; trong cùng mode theo priority tăng dần."""
    raw = (category_name or '').strip()
    if not raw:
        return None
    maps = list(
        ProductTypeKvMap.objects.filter(is_active=True, product_type__is_active=True)
        .select_related('product_type')
        .order_by('priority', 'id')
    )
    folded = raw.casefold()
    for row in maps:
        if row.match_mode == KV_MAP_MATCH_EXACT and row.match_value.casefold() == folded:
            return row.product_type
    for row in maps:
        needle = (row.match_value or '').strip()
        if row.match_mode == KV_MAP_MATCH_CONTAINS and needle and needle.casefold() in folded:
            return row.product_type
    return None


def seed_default_product_types() -> int:
    from kho_san_pham.choices import DEFAULT_CATALOG_TYPES

    created = 0
    for code, name, order in DEFAULT_CATALOG_TYPES:
        _, was = ProductType.objects.get_or_create(
            code=code,
            defaults={'name': name, 'sort_order': order, 'is_active': True},
        )
        if was:
            created += 1
    return created
