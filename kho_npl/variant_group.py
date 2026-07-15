"""Suy luận và chuẩn hóa tên nhóm hàng (biến thể) từ mã NPL."""

from __future__ import annotations

import re

# Tiền tố nhóm trong mã chuẩn (VAI-, BO-, BB-, …) hoặc JP- cũ.
_PREFIX_RE = re.compile(
    r'^(?:'
    r'VAI|VPH|BO|DK|DR|NUT|KHOEN|TEM|BB|DC|CHI|PK|JP'
    r')-',
    re.IGNORECASE,
)
_TRAILING_SEQ_RE = re.compile(r'[-_]?\d{1,4}$')
_TRAILING_LETTER_SEQ_RE = re.compile(r'[-_][A-Z]{1,3}$', re.IGNORECASE)


def normalize_variant_group(value: str | None) -> str:
    """Chuẩn hóa tên nhóm hàng — viết hoa, cắt khoảng trắng."""
    return (value or '').strip().upper()


def infer_variant_group_from_code(code: str | None) -> str:
    """
    Suy nhóm hàng từ mã NPL đã chuẩn hóa.

    Ví dụ:
      VAI-SIEU-01 → SIEU
      VAI-CR3-04 → CR3
      BB-BICH-01 → BICH
      JP-NUT-01 → NUT
      VAI-CASAU → CASAU
      PK-AC → AC
    """
    code = (code or '').strip().upper()
    if not code:
        return ''

    rest = _PREFIX_RE.sub('', code, count=1) if _PREFIX_RE.match(code) else code
    rest = rest.strip('-_ ')
    if not rest:
        return code

    # Bỏ số thứ tự cuối: -01, -001, _12
    base = _TRAILING_SEQ_RE.sub('', rest).strip('-_ ')
    if not base:
        # Mã chỉ còn số sau tiền tố — dùng phần rest đầy đủ
        return rest

    # Giữ phần chữ/ số chất liệu (CR3, L6.3, MK11.2, …)
    return base
