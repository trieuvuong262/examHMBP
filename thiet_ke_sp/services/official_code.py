"""Gợi ý mã sản phẩm chính thức khi duyệt thiết kế.

Mẫu giống Style trong Danh mục sản phẩm: ``JP-TEE-00-SP8516975``.
Số SP kế tiếp = số SP lớn nhất của loại đó trong Danh mục + số size chuẩn (17).
Mã chỉ được điền khi chưa có trong Danh mục (mã gốc, SKU mã-size) và chưa có Style.
"""

from __future__ import annotations

from django.db.models import BigIntegerField, Q
from django.db.models.expressions import RawSQL

from kho_san_pham.catalog_models import ProductStyle
from kho_san_pham.choices import DEFAULT_BRAND, DEFAULT_STYLE_GROUP
from kho_san_pham.models import Product
from kho_san_pham.services.code_structure import (
    compose_style_code,
    normalize_type_code,
    type_code_has_group,
)
from kho_san_pham.sku_vocabulary import SP_NUMBER_RE
from thiet_ke_sp.services.size_spec import SIZE_SPEC_SIZES

SIZE_STEP = len(SIZE_SPEC_SIZES)

_SP_SQL = (
    "COALESCE((regexp_match(COALESCE(NULLIF(BTRIM(style_code), ''), code),"
    " 'SP([0-9]+)'))[1]::bigint, -1)"
)
_STYLE_SP_SQL = "COALESCE((regexp_match(code, 'SP([0-9]+)'))[1]::bigint, -1)"


def type_code_of(dossier) -> str:
    """Loại mã trên hồ sơ; không có thì dùng nhóm sản phẩm."""
    catalog = getattr(dossier, 'product_type', None)
    if getattr(dossier, 'product_type_id', None) and catalog is not None:
        return normalize_type_code(catalog.code)
    return normalize_type_code(getattr(dossier, 'product_group', ''))


def official_code_suggestion(dossier, cache: dict | None = None) -> str:
    """Mã điền sẵn. Hồ sơ đã có mã thì giữ. ``cache`` để vài hồ sơ cùng loại không trùng một số."""
    existing = (getattr(dossier, 'official_product_code', '') or '').strip().upper()
    if existing:
        return existing
    type_code = type_code_of(dossier)
    if not type_code:
        return ''
    if cache is None:
        cache = {}
    state = cache.get(type_code)
    if state is None:
        number, width = _first_free(type_code, _start_number(type_code))
        state = {'next': number, 'width': width}
        cache[type_code] = state
    else:
        state['next'], state['width'] = _first_free(type_code, state['next'], state['width'])
    if state['next'] <= 0:
        return ''
    code = _compose(type_code, state['next'], state['width'])
    state['next'] += SIZE_STEP
    return code


def _style_prefix(type_code: str) -> str:
    if type_code_has_group(type_code):
        return f'{DEFAULT_BRAND}-{type_code}-SP'
    return f'{DEFAULT_BRAND}-{type_code}-{DEFAULT_STYLE_GROUP}-SP'


def style_taken_in_catalog(code: str) -> str:
    """Mã gốc đã có sản phẩm hoặc Style trong Danh mục. Rỗng nếu còn trống."""
    code = (code or '').strip().upper()
    if not code:
        return ''
    sku_prefix = f'{code}-'
    if Product.objects.filter(
        Q(style_code__iexact=code) | Q(code__iexact=code) | Q(code__istartswith=sku_prefix),
    ).exists():
        return f'Mã {code} đã có trong Danh mục sản phẩm.'
    if ProductStyle.objects.filter(code__iexact=code).exists():
        return f'Mã {code} đã có trong Danh mục sản phẩm.'
    return ''


def _product_qs(prefix: str | None):
    qs = Product.objects.all()
    if prefix:
        return qs.filter(Q(style_code__istartswith=prefix) | Q(code__istartswith=prefix))
    return qs.filter(Q(style_code__icontains='SP') | Q(code__icontains='SP'))


def _style_qs(prefix: str | None):
    qs = ProductStyle.objects.all()
    if prefix:
        return qs.filter(code__istartswith=prefix)
    return qs.filter(code__icontains='SP')


def _max_labeled(qs, sql: str) -> tuple[int, int]:
    row = (
        qs.annotate(_sp=RawSQL(sql, [], output_field=BigIntegerField()))
        .filter(_sp__gt=0)
        .order_by('-_sp')
        .values_list('code', '_sp')
        .first()
    )
    if not row:
        return 0, 0
    code, number = row
    match = SP_NUMBER_RE.search(code or '')
    width = len(match.group(1)) if match else len(str(int(number)))
    return int(number), width


def _max_sp(prefix: str | None) -> tuple[int, int]:
    """Số SP lớn nhất trong Danh mục, kể cả sản phẩm ngừng bán và Style chưa có SKU."""
    product_number, product_width = _max_labeled(_product_qs(prefix), _SP_SQL)
    style_number, style_width = _max_labeled(_style_qs(prefix), _STYLE_SP_SQL)
    if style_number > product_number:
        return style_number, style_width or product_width
    return product_number, product_width or style_width


def _start_number(type_code: str) -> tuple[int, int]:
    number, width = _max_sp(_style_prefix(type_code))
    if number <= 0:
        number, width = _max_sp(None)
    if number <= 0:
        return 0, 0
    return number + SIZE_STEP, width


def _compose(type_code: str, number: int, width: int) -> str:
    root = f'SP{number:0{width}d}'
    if type_code_has_group(type_code):
        suffix = root
    else:
        suffix = f'{DEFAULT_STYLE_GROUP}-{root}'
    return compose_style_code(brand=DEFAULT_BRAND, type_code=type_code, suffix=suffix)


def _taken(type_code: str, number: int, width: int) -> bool:
    from thiet_ke_sp.services.workflow import official_code_conflict

    return bool(official_code_conflict(_compose(type_code, number, width)))


def _first_free(type_code: str, start: tuple[int, int] | int, width: int | None = None) -> tuple[int, int]:
    if isinstance(start, tuple):
        number, width = start
    else:
        number = start
        width = width or len(str(number))
    if number <= 0:
        return 0, 0
    for _ in range(200):
        if not _taken(type_code, number, width):
            return number, width
        number += SIZE_STEP
    return number, width
