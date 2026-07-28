"""Đồng bộ thành phẩm 1 chiều: kv_product (mirror) → kho_sp_product.

- Tạo mới khi chưa có (theo kiotviet_id / mã).
- Bổ sung Size/Màu trống từ thuộc tính KV.
- Khi có map nhóm hàng → loại: gom size, mã gốc = size nhỏ nhất,
  Style ``JP-{LOẠI}-{NHÓM}-{ROOT}`` (vd. ``JP-JKT-00-SP007105``, ``JP-SET-SC-SP002771``),
  SKU ``{Style}-{Size}`` (có màu thì thêm màu).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from kho_san_pham.choices import (
    DEFAULT_BRAND,
    PRODUCT_TYPE_THANH_PHAM,
    SYNC_SOURCE_KIOTVIET,
)
from kho_san_pham.models import Product

_SIZE_ATTR_NAMES = frozenset({
    'size', 'kích cỡ', 'kich co', 'cỡ', 'co',
})
_COLOR_ATTR_NAMES = frozenset({
    'màu', 'mau', 'color', 'colour',
})
_DEFAULT_UNIT = 'Cái'

# Màu thường gặp trong tên SP khi KV không có thuộc tính MÀU
_COLOR_NAME_HINTS = (
    'xanh chuối', 'xanh đen', 'xanh bích', 'xanh da', 'xanh dương', 'xanh lá',
    'xanh navy', 'xanh ngọc', 'xanh biển', 'xanh lý', 'hồng đất', 'vàng chanh',
    'cam đất', 'cổ vịt', 'lông công', 'trắng đen', 'trắng hồng', 'trắng cam',
    'trắng xanh', 'đen chuối',
    'trắng', 'đen', 'đỏ', 'cam', 'vàng', 'hồng', 'tím', 'nâu', 'be', 'xám',
    'bạc', 'kem', 'navy', 'chuối', 'ngọc', 'bích', 'biển', 'xanh',
)

_FALLBACK_SIZE_ORDER = {
    'XXS': 5, '2XS': 5, 'XS': 10, 'S': 20, 'M': 30, 'L': 40,
    'XL': 50, 'XXL': 60, '2XL': 60, '3XL': 70, 'XXXL': 70, '4XL': 80,
}

_color_vocab_cache: list[str] | None = None


def _color_vocab(*, retailer: str | None = None) -> list[str]:
    """Danh sách màu (dài → ngắn) từ thuộc tính KV + gợi ý cố định."""
    global _color_vocab_cache
    if _color_vocab_cache is not None and retailer is None:
        return _color_vocab_cache
    values = set(_COLOR_NAME_HINTS)
    try:
        from kiotviet.models import KvProductAttribute
        from kiotviet.sync_service import current_retailer
        r = retailer or current_retailer()
        if r:
            for val in (
                KvProductAttribute.objects
                .filter(retailer=r, attribute_name__iexact='MÀU')
                .exclude(attribute_value='')
                .values_list('attribute_value', flat=True)
                .distinct()
            ):
                v = (val or '').strip()
                if v:
                    values.add(v.casefold())
                    values.add(v)
    except Exception:  # noqa: BLE001
        pass
    # Chuẩn hoá: giữ bản gốc có dấu nếu có
    normalized: dict[str, str] = {}
    for v in values:
        key = v.casefold()
        if key not in normalized or any(c.isupper() for c in v) or ' ' in v:
            # Ưu tiên bản có dấu tiếng Việt (không casefold làm mất dấu — casefold giữ dấu)
            if key not in normalized:
                normalized[key] = v.strip()
            else:
                # Prefer longer / title-like
                cur = normalized[key]
                if len(v) > len(cur):
                    normalized[key] = v.strip()
    ordered = sorted(normalized.values(), key=lambda s: (-len(s), s.casefold()))
    if retailer is None:
        _color_vocab_cache = ordered
    return ordered


def _color_from_name(name: str, *, retailer: str | None = None) -> str:
    """Tách màu từ tên SP — chỉ khớp token (tránh 'cam' trong 'Camaro')."""
    import re

    text = (name or '').strip()
    if not text:
        return ''
    folded = text.casefold()
    for color in _color_vocab(retailer=retailer):
        needle = color.casefold().strip()
        if not needle:
            continue
        # Ranh giới: không liền chữ cái / số (Camaro ≠ cam)
        pattern = re.compile(
            rf'(?<![0-9a-zàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ])'
            rf'{re.escape(needle)}'
            rf'(?![0-9a-zàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ])',
            re.IGNORECASE,
        )
        m = pattern.search(folded)
        if m:
            return text[m.start():m.end()].strip() or color
    return ''



@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    deactivated: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = [f'tạo mới {self.created}', f'bỏ qua (đã có) {self.skipped}']
        if self.updated:
            parts.append(f'cập nhật / bổ sung {self.updated}')
        if self.deactivated:
            parts.append(f'ngừng {self.deactivated}')
        if self.errors:
            parts.append(f'lỗi {len(self.errors)}')
        return ' · '.join(parts)


def _first_image_url(kv) -> str:
    urls = getattr(kv, 'image_urls', None) or []
    for url in urls:
        if url:
            return str(url).strip()
    return ''


def _find_existing(kv) -> Product | None:
    if kv.kiotviet_id is not None:
        found = Product.objects.filter(kiotviet_id=kv.kiotviet_id).first()
        if found:
            return found
    code = (kv.code or '').strip()
    if code:
        found = Product.objects.filter(kiotviet_code__iexact=code).first()
        if found:
            return found
        found = Product.objects.filter(code__iexact=code).first()
        if found:
            return found
    return None


def _attrs_from_kv(kv, *, retailer: str) -> list[tuple[str, str]]:
    from kiotviet.models import KvProductAttribute

    if kv.kiotviet_id is None:
        return []
    return list(
        KvProductAttribute.objects.filter(
            retailer=retailer,
            product_kiotviet_id=kv.kiotviet_id,
        ).values_list('attribute_name', 'attribute_value')
    )


def _size_from_attrs(attrs: list[tuple[str, str]]) -> str:
    for name, value in attrs:
        key = (name or '').strip().lower()
        if key in _SIZE_ATTR_NAMES or 'size' in key or 'cỡ' in key:
            val = (value or '').strip()
            if val:
                return val
    return ''


def _color_from_attrs(attrs: list[tuple[str, str]]) -> str:
    for name, value in attrs:
        key = (name or '').strip().lower()
        if key in _COLOR_ATTR_NAMES or 'color' in key or 'màu' in key:
            val = (value or '').strip()
            if val:
                return val
    return ''


def _size_sort_key(size_label: str) -> tuple:
    label = (size_label or '').strip().upper()
    if not label:
        return (9999, '')
    try:
        from san_xuat.hub_models import SxSize
        row = SxSize.objects.filter(code__iexact=label).first()
        if row:
            return (int(row.sort_order), label)
    except Exception:  # noqa: BLE001
        pass
    if label in _FALLBACK_SIZE_ORDER:
        return (_FALLBACK_SIZE_ORDER[label], label)
    if label.isdigit():
        return (1000 + int(label), label)
    return (5000, label)


def _group_key(name: str, color_label: str) -> str:
    base = (name or '').strip().casefold() or '—'
    color = (color_label or '').strip().casefold()
    return f'{base}||{color}'


def _is_matrix_size(size_label: str) -> bool:
    """Size ma trận (S/M/L/…) — khác OS / trống (phụ kiện 1 mã = 1 Style)."""
    label = (size_label or '').strip().upper()
    if not label or label in {'OS', 'ONE', 'ONESIZE', 'FREE', 'F'}:
        return False
    return True


def _variant_group_key(*, name: str, color_label: str, size_label: str, kiotviet_code: str) -> str:
    """Gom size thật theo tên+màu; không size → mỗi mã KV một nhóm."""
    if _is_matrix_size(size_label):
        return _group_key(name, color_label)
    code = (kiotviet_code or '').strip().upper() or '—'
    return f'single:{code}'


def _is_temp_code(product: Product) -> bool:
    """SKU tạm = trùng mã KV hoặc trống Style chuẩn JP-… hoặc gắn ID KV đuôi."""
    import re

    kv = (product.kiotviet_code or '').strip().upper()
    code = (product.code or '').strip().upper()
    style = (product.style_code or '').strip().upper()
    if not style:
        return True
    if kv and code == kv:
        return True
    if style and not style.startswith(f'{DEFAULT_BRAND}-'):
        # Style cũ = tên SP từ lần sync trước
        return True
    # JP-…-OS-31972720 (đụng SKU rồi gắn kiotviet_id)
    if re.search(r'-\d{6,}$', code):
        return True
    return False


def _compose_variant_sku(*, style_code: str, color_code: str, size_label: str) -> str:
    from san_xuat.services.sku_catalog import compose_sku_code

    return compose_sku_code(
        style_code=style_code,
        color_code=color_code or '',
        size_label=size_label,
    )


def _build_base_fields(kv, *, retailer: str) -> dict:
    attrs = _attrs_from_kv(kv, retailer=retailer)
    size_label = _size_from_attrs(attrs).upper()
    color_label = _color_from_attrs(attrs)
    kiotviet_code = (kv.code or '').strip()
    name = (kv.name or kv.full_name or kv.code or '').strip() or kiotviet_code
    if not color_label:
        color_label = _color_from_name(name, retailer=retailer)
    color_code = ''
    # Chỉ gán mã màu ngắn ASCII (NVY, BLK…) — không upper-case nhãn tiếng Việt (đen→ĐEN)
    if color_label:
        token = color_label.replace(' ', '').strip()
        if token.isascii() and token.isalnum() and 1 < len(token) <= 8:
            color_code = token.upper()

    unit = (kv.unit or '').strip() or _DEFAULT_UNIT
    return {
        'kiotviet_code': kiotviet_code,
        'name': name,
        'full_name': (kv.full_name or '').strip(),
        'bar_code': (kv.bar_code or '').strip(),
        'unit': unit,
        'category_name': (kv.category_name or '').strip(),
        'category_path': (getattr(kv, 'category_path', None) or '').strip(),
        'description': (kv.description or '').strip(),
        'allows_sale': kv.allows_sale,
        'is_active': False if kv.is_active is False else True,
        'image_url': _first_image_url(kv),
        'kv_modified_at': kv.kv_modified_at,
        'size_label': size_label,
        'color_label': color_label,
        'color_code': color_code,
        'base_price': Decimal(str(kv.base_price)) if kv.base_price is not None else None,
        'attrs': attrs,
    }


def _apply_style_to_product(
    product: Product,
    *,
    catalog_type,
    style,
    size_label: str,
    color_code: str,
    color_label: str,
    force_sku: bool,
) -> bool:
    """Gán catalog_type / style / SKU. Trả True nếu có thay đổi."""
    changed = False
    if product.catalog_type_id != catalog_type.pk:
        product.catalog_type = catalog_type
        changed = True
    if (product.style_code or '').strip().upper() != style.code:
        product.style_code = style.code
        changed = True
    if size_label and (product.size_label or '').strip().upper() != size_label:
        product.size_label = size_label
        changed = True
    if color_code and not (product.color_code or '').strip():
        product.color_code = color_code
        changed = True
    if color_label and not (product.color_label or '').strip():
        product.color_label = color_label
        changed = True

    if size_label and (force_sku or _is_temp_code(product)):
        try:
            new_sku = _compose_variant_sku(
                style_code=style.code,
                color_code=product.color_code or color_code,
                size_label=size_label,
            )
        except Exception:  # noqa: BLE001
            new_sku = ''
        if new_sku and (product.code or '').strip().upper() != new_sku:
            clash = (
                Product.objects.filter(code__iexact=new_sku)
                .exclude(pk=product.pk)
                .exists()
            )
            if not clash:
                product.code = new_sku
                changed = True
            # Trùng SKU: không gắn ID vào mã — để bước nhóm single-SKU sửa Style

    if changed:
        product.synced_at = timezone.now()
        product.save()
    return changed


def _create_product_from_kv(kv, fields: dict, *, style_code: str, code: str, catalog_type=None) -> Product:
    from kho_san_pham.services.barcode import allocate_barcode

    bar_code = (fields.get('bar_code') or '').strip() or allocate_barcode()
    product = Product(
        code=code,
        style_code=style_code,
        color_code=fields['color_code'],
        color_label=fields['color_label'],
        size_label=fields['size_label'],
        product_type=PRODUCT_TYPE_THANH_PHAM,
        catalog_type=catalog_type,
        sync_source=SYNC_SOURCE_KIOTVIET,
        kiotviet_id=kv.kiotviet_id,
        kiotviet_code=fields['kiotviet_code'],
        name=fields['name'],
        full_name=fields['full_name'],
        bar_code=bar_code,
        unit=fields['unit'],
        category_name=fields['category_name'],
        category_path=fields['category_path'],
        description=fields['description'],
        allows_sale=fields['allows_sale'],
        is_active=fields['is_active'],
        image_url=fields['image_url'],
        kv_modified_at=fields['kv_modified_at'],
        synced_at=timezone.now(),
    )
    if fields['base_price'] is not None:
        product.base_price = fields['base_price']
    product.save()
    return product


@transaction.atomic
def sync_thanh_pham_from_kiotviet(*, retailer: str | None = None, deactivate_missing: bool = False) -> SyncResult:
    from kiotviet.models import KvProduct
    from kiotviet.sync_service import current_retailer
    from kho_san_pham.services.code_structure import get_or_create_kv_style, resolve_type_for_category

    result = SyncResult()
    retailer = retailer if retailer is not None else current_retailer()
    if not retailer:
        result.errors.append('KIOTVIET_RETAILER chưa cấu hình.')
        return result

    qs = list(
        KvProduct.objects
        .filter(retailer=retailer, is_deleted=False)
        .exclude(code='')
        .order_by('code', 'kiotviet_id')
    )

    # Gom theo tên + màu (size ma trận) hoặc từng mã KV (không size / OS)
    buckets: dict[str, list[tuple]] = defaultdict(list)
    for kv in qs:
        fields = _build_base_fields(kv, retailer=retailer)
        key = _variant_group_key(
            name=fields['name'],
            color_label=fields['color_label'],
            size_label=fields['size_label'],
            kiotviet_code=fields['kiotviet_code'],
        )
        buckets[key].append((kv, fields))

    for _key, items in buckets.items():
        items.sort(key=lambda pair: (
            _size_sort_key(pair[1]['size_label']),
            (pair[1]['kiotviet_code'] or '').upper(),
            pair[0].kiotviet_id or 0,
        ))
        root_fields = items[0][1]
        root_kv_code = root_fields['kiotviet_code']
        catalog_type = resolve_type_for_category(root_fields['category_name'])
        style = None
        if catalog_type and root_kv_code:
            try:
                style, _ = get_or_create_kv_style(
                    product_type=catalog_type,
                    root_kiotviet_code=root_kv_code,
                    name=root_fields['name'],
                    brand=DEFAULT_BRAND,
                )
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f'Style {root_kv_code}: {exc}'[:200])
                style = None

        for kv, fields in items:
            try:
                existing = _find_existing(kv)
                size_label = fields['size_label']

                if existing is not None:
                    changed = False
                    # Bổ sung size/color/unit trống
                    if not (existing.size_label or '').strip() and size_label:
                        existing.size_label = size_label
                        changed = True
                    if not (existing.color_label or '').strip() and fields['color_label']:
                        existing.color_label = fields['color_label']
                        changed = True
                    if not (existing.color_code or '').strip() and fields['color_code']:
                        existing.color_code = fields['color_code']
                        changed = True
                    if not (existing.unit or '').strip() and fields['unit']:
                        existing.unit = fields['unit']
                        changed = True
                    if not (existing.bar_code or '').strip():
                        from kho_san_pham.services.barcode import allocate_barcode
                        existing.bar_code = fields['bar_code'] or allocate_barcode()
                        changed = True

                    effective_size = (size_label or existing.size_label or '').strip().upper()
                    if style and catalog_type and not effective_size:
                        effective_size = 'OS'
                    if style and catalog_type and effective_size:
                        if _apply_style_to_product(
                            existing,
                            catalog_type=catalog_type,
                            style=style,
                            size_label=effective_size,
                            color_code=fields['color_code'],
                            color_label=fields['color_label'],
                            force_sku=False,
                        ):
                            result.updated += 1
                        elif changed:
                            existing.synced_at = timezone.now()
                            existing.save()
                            result.updated += 1
                        else:
                            result.skipped += 1
                    elif changed:
                        # Style chưa map: vẫn lưu size; style tạm = tên nếu trống
                        if not (existing.style_code or '').strip():
                            existing.style_code = fields['name'][:80]
                        existing.synced_at = timezone.now()
                        existing.save()
                        result.updated += 1
                    else:
                        result.skipped += 1
                    continue

                # Tạo mới
                create_size = size_label or ('OS' if catalog_type else '')
                if style and catalog_type and create_size:
                    try:
                        sku = _compose_variant_sku(
                            style_code=style.code,
                            color_code=fields['color_code'],
                            size_label=create_size,
                        )
                    except Exception:
                        sku = fields['kiotviet_code'] or f'KV-{kv.kiotviet_id}'
                    if Product.objects.filter(code__iexact=sku).exists():
                        # Trùng (thường OS): Style = mã KV của chính SP — không gắn ID đuôi
                        own = fields['kiotviet_code']
                        if own and catalog_type and (
                            own != root_kv_code or not _is_matrix_size(create_size)
                        ):
                            style_own, _ = get_or_create_kv_style(
                                product_type=catalog_type,
                                root_kiotviet_code=own,
                                name=fields['name'],
                                brand=DEFAULT_BRAND,
                            )
                            style = style_own
                            sku = _compose_variant_sku(
                                style_code=style.code,
                                color_code=fields['color_code'],
                                size_label=create_size,
                            )
                        if Product.objects.filter(code__iexact=sku).exists():
                            # Fallback tạm = mã KV (không JP-…-OS-{id})
                            sku = own or f'KV-{kv.kiotviet_id}'
                    fields_create = dict(fields)
                    fields_create['size_label'] = create_size
                    _create_product_from_kv(
                        kv, fields_create,
                        style_code=style.code,
                        code=sku,
                        catalog_type=catalog_type,
                    )
                else:
                    code = fields['kiotviet_code'] or f'KV-{kv.kiotviet_id}'
                    if Product.objects.filter(code__iexact=code).exists():
                        code = f'KV-{kv.kiotviet_id}'
                    style_tmp = (fields['name'] or '')[:80]
                    _create_product_from_kv(
                        kv, fields,
                        style_code=style_tmp,
                        code=code,
                        catalog_type=None,
                    )
                result.created += 1
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f'KV#{kv.kiotviet_id} {kv.code}: {exc}'[:200])

    if deactivate_missing:
        active_kv_ids = {p.kiotviet_id for p in qs if p.kiotviet_id is not None}
        stale = (
            Product.objects
            .filter(product_type=PRODUCT_TYPE_THANH_PHAM, sync_source=SYNC_SOURCE_KIOTVIET, is_active=True)
            .exclude(kiotviet_id__isnull=True)
            .exclude(kiotviet_id__in=active_kv_ids)
        )
        result.deactivated = stale.update(is_active=False, synced_at=timezone.now())

    return result


@transaction.atomic
def apply_style_sku_for_existing_products() -> SyncResult:
    """Gán loại + sinh Style/SKU cho SP KV còn mã tạm (dùng map đã cấu hình)."""
    from kiotviet.models import KvProduct
    from kiotviet.sync_service import current_retailer
    from kho_san_pham.services.code_structure import get_or_create_kv_style, resolve_type_for_category

    result = SyncResult()
    retailer = current_retailer()
    if not retailer:
        result.errors.append('KIOTVIET_RETAILER chưa cấu hình.')
        return result

    products = list(
        Product.objects.filter(sync_source=SYNC_SOURCE_KIOTVIET)
        .exclude(kiotviet_id__isnull=True)
    )
    kv_by_id = {
        row.kiotviet_id: row
        for row in KvProduct.objects.filter(
            retailer=retailer,
            kiotviet_id__in=[p.kiotviet_id for p in products],
            is_deleted=False,
        )
    }

    buckets: dict[str, list[Product]] = defaultdict(list)
    meta: dict[int, dict] = {}
    for product in products:
        kv = kv_by_id.get(product.kiotviet_id)
        if not kv:
            result.skipped += 1
            continue
        fields = _build_base_fields(kv, retailer=retailer)
        if not (product.size_label or '').strip() and fields['size_label']:
            product.size_label = fields['size_label']
        if not (product.color_label or '').strip() and fields['color_label']:
            product.color_label = fields['color_label']
        if not (product.color_code or '').strip() and fields['color_code']:
            product.color_code = fields['color_code']
        if not (product.unit or '').strip() and fields['unit']:
            product.unit = fields['unit']
        meta[product.pk] = fields
        size_for_group = (product.size_label or fields.get('size_label') or '').strip()
        key = _variant_group_key(
            name=fields['name'] or product.name,
            color_label=fields['color_label'] or product.color_label,
            size_label=size_for_group,
            kiotviet_code=fields.get('kiotviet_code') or product.kiotviet_code,
        )
        buckets[key].append(product)

    for _key, group in buckets.items():
        group.sort(key=lambda p: (
            _size_sort_key(p.size_label or (meta.get(p.pk) or {}).get('size_label', '')),
            (p.kiotviet_code or '').upper(),
            p.pk,
        ))
        root = group[0]
        root_fields = meta.get(root.pk) or {}
        root_kv = (root.kiotviet_code or root_fields.get('kiotviet_code') or '').strip()
        category = root_fields.get('category_name') or root.category_name
        catalog_type = resolve_type_for_category(category)
        if not catalog_type or not root_kv:
            result.skipped += len(group)
            continue
        try:
            style, _ = get_or_create_kv_style(
                product_type=catalog_type,
                root_kiotviet_code=root_kv,
                name=root_fields.get('name') or root.name,
            )
        except Exception as exc:  # noqa: BLE001
            result.errors.append(str(exc)[:200])
            result.skipped += len(group)
            continue

        for product in group:
            fields = meta.get(product.pk) or {}
            size_label = (product.size_label or fields.get('size_label') or '').strip().upper()
            if not size_label:
                size_label = 'OS'
            if _apply_style_to_product(
                product,
                catalog_type=catalog_type,
                style=style,
                size_label=size_label,
                color_code=fields.get('color_code') or product.color_code,
                color_label=fields.get('color_label') or product.color_label,
                force_sku=_is_temp_code(product) or (
                    not _is_matrix_size(size_label)
                    and (product.kiotviet_code or '').strip().upper()
                    and style.root_kiotviet_code.upper() != (product.kiotviet_code or '').strip().upper()
                ),
            ):
                result.updated += 1
            else:
                result.skipped += 1

    # Sửa phụ kiện one-size còn gắn đuôi kiotviet_id
    repair = repair_single_sku_os_codes()
    result.updated += repair.updated
    result.errors.extend(repair.errors)

    # Chèn nhóm mặc định 00 (JP-JKT-SP… → JP-JKT-00-SP…)
    repair_g = repair_default_style_group()
    result.updated += repair_g.updated
    result.errors.extend(repair_g.errors)

    return result


def _style_missing_default_group(style_code: str) -> bool:
    """True nếu Style dạng ``JP-JKT-SP007105`` (thiếu nhóm 00)."""
    parts = (style_code or '').strip().upper().split('-')
    return (
        len(parts) == 3
        and parts[0] == DEFAULT_BRAND
        and parts[2].startswith('SP')
    )


@transaction.atomic
def repair_default_style_group() -> SyncResult:
    """Chèn nhóm mặc định ``00``: ``JP-JKT-SP007105`` → ``JP-JKT-00-SP007105``.

    Loại đã có nhóm trong mã (``SET-SC``, ``ACC-BALO``) giữ nguyên.
    """
    from kho_san_pham.catalog_models import ProductStyle, ProductType
    from kho_san_pham.services.code_structure import get_or_create_kv_style, type_code_has_group

    result = SyncResult()
    qs = (
        Product.objects.filter(sync_source=SYNC_SOURCE_KIOTVIET)
        .exclude(style_code='')
        .select_related('catalog_type')
    )
    for product in qs.iterator(chunk_size=200):
        if not _style_missing_default_group(product.style_code):
            result.skipped += 1
            continue
        parts = product.style_code.strip().upper().split('-')
        catalog_type = product.catalog_type
        if not catalog_type:
            catalog_type = ProductType.objects.filter(code__iexact=parts[1]).first()
        if not catalog_type or type_code_has_group(catalog_type.code):
            result.skipped += 1
            continue

        root = parts[2]
        old_style = ProductStyle.objects.filter(code__iexact=product.style_code).first()
        if old_style and old_style.root_kiotviet_code:
            root = old_style.root_kiotviet_code

        try:
            style, _ = get_or_create_kv_style(
                product_type=catalog_type,
                root_kiotviet_code=root,
                name=product.name,
                brand=DEFAULT_BRAND,
            )
        except Exception as exc:  # noqa: BLE001
            result.errors.append((f'{product.code}: {exc}')[:200])
            continue

        size = (product.size_label or '').strip().upper() or 'OS'
        try:
            sku = _compose_variant_sku(
                style_code=style.code,
                color_code=product.color_code or '',
                size_label=size,
            )
        except Exception as exc:  # noqa: BLE001
            result.errors.append((f'{product.code}: {exc}')[:200])
            continue

        if (
            (product.style_code or '').upper() == style.code
            and (product.code or '').upper() == sku.upper()
        ):
            result.skipped += 1
            continue

        clash = Product.objects.filter(code__iexact=sku).exclude(pk=product.pk).exists()
        if clash:
            # Vẫn nâng Style (có nhóm); giữ mã hiện tại nếu SKU chuẩn bị trùng
            if (product.style_code or '').upper() != style.code:
                product.style_code = style.code
                if product.catalog_type_id != catalog_type.pk:
                    product.catalog_type = catalog_type
                product.synced_at = timezone.now()
                product.save()
                result.updated += 1
                result.errors.append(
                    f'{product.kiotviet_code or product.pk}: Style → {style.code}, SKU giữ {product.code} (trùng {sku})'
                )
            else:
                result.errors.append(f'{product.kiotviet_code or product.pk}: SKU {sku} đã tồn tại')
                result.skipped += 1
            continue

        product.style_code = style.code
        product.code = sku
        if product.catalog_type_id != catalog_type.pk:
            product.catalog_type = catalog_type
        product.synced_at = timezone.now()
        product.save()
        result.updated += 1

    return result


@transaction.atomic
def repair_single_sku_os_codes() -> SyncResult:
    """Sửa phụ kiện / SP không size: mỗi mã KV → Style riêng ``JP-TYPE-{KV}``, SKU ``…-OS``.

    Xử lý mã lệch dạng ``JP-ACC-SP8516465-OS-31972720``.
    """
    import re

    from kho_san_pham.services.code_structure import get_or_create_kv_style

    result = SyncResult()
    qs = (
        Product.objects.filter(sync_source=SYNC_SOURCE_KIOTVIET)
        .exclude(kiotviet_code='')
        .exclude(catalog_type_id=None)
        .select_related('catalog_type')
    )
    for product in qs.iterator(chunk_size=200):
        size = (product.size_label or '').strip().upper() or 'OS'
        # Ma trận size giữ group theo tên — chỉ sửa SP one-size / phụ kiện
        if _is_matrix_size(size):
            result.skipped += 1
            continue
        own_kv = (product.kiotviet_code or '').strip()
        if not own_kv or not product.catalog_type_id:
            result.skipped += 1
            continue
        try:
            style, _ = get_or_create_kv_style(
                product_type=product.catalog_type,
                root_kiotviet_code=own_kv,
                name=product.name,
                brand=DEFAULT_BRAND,
            )
            sku = _compose_variant_sku(
                style_code=style.code,
                color_code=product.color_code or '',
                size_label=size,
            )
        except Exception as exc:  # noqa: BLE001
            result.errors.append((f'{own_kv}: {exc}')[:200])
            continue

        if (
            (product.style_code or '').upper() == style.code
            and (product.code or '').upper() == sku.upper()
            and (product.size_label or '').upper() == size
        ):
            result.skipped += 1
            continue

        clash = Product.objects.filter(code__iexact=sku).exclude(pk=product.pk).exists()
        if clash:
            # Nếu chính mã đích đang thuộc SP khác có cùng KV style đúng — bỏ qua
            result.errors.append(f'{own_kv}: SKU {sku} đã tồn tại')
            result.skipped += 1
            continue

        product.style_code = style.code
        product.code = sku
        product.size_label = size
        product.synced_at = timezone.now()
        product.save(update_fields=['style_code', 'code', 'size_label', 'synced_at', 'updated_at'])
        result.updated += 1

    return result
