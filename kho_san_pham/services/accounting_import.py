"""Nhập mã kế toán từ file danh sách HĐ / tem nhãn / Kiot (cột Mã sản phẩm + Tên Kiot)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import openpyxl
from django.db import transaction
from django.db.models import Q

from kho_san_pham.models import Product

# Chuẩn hoá từ khoá trong file → chuỗi tìm trên tên SP portal
_KEYWORD_ALIASES: dict[str, list[str]] = {
    'liver pool': ['liver', 'liverpool'],
    'liverpool': ['liver', 'liverpool'],
    'mancity': ['man city', 'mancity'],
    'man city': ['man city', 'mancity'],
    'braca': ['barca', 'barcelona'],
    'barca': ['barca', 'barcelona'],
    'bồ đào nha': ['bồ đào nha', 'bo dao nha', 'portugal'],
    'phanther': ['panther'],
    'panther ii': ['panther'],
    'volly': ['volly', 'volley'],
    'mu': ['manchester united', 'man utd', ' man u', 'mu '],
    'lighting': ['lighting', 'lightling'],
    'flick': ['flick'],
    'smaro': ['smaro'],
    'smash': ['smash'],
    'drop': ['drop'],
    'rockfire': ['rockfire'],
    'stormbreak': ['stormbreak'],
    'jumper': ['jumper'],
    'tottenham': ['tottenham', 'totte'],
    'bayern': ['bayern'],
    'brazil': ['brazil', 'brasil'],
    'acr milan': ['ac milan', 'milan'],
    'ac milan': ['ac milan', 'milan'],
    'inter': ['inter'],
    'juve': ['juve', 'juventus'],
    'croatia': ['croatia', 'croatia'],
    'hà lan': ['hà lan', 'ha lan', 'holland', 'netherlands'],
    'bỉ': ['bỉ', 'bi ', 'belgium'],
    'nhật bản': ['nhật', 'nhat', 'japan'],
    'hàn quốc': ['hàn', 'han quoc', 'korea'],
}

_STOP_TOKENS = frozenset({
    'quan', 'áo', 'ao', 'quần', 'bóng', 'bong', 'đá', 'da', 'clb', 'nam', 'nữ', 'nu',
    'các', 'cac', 'màu', 'mau', 'size', 'và', 'va', 'the', 'thao', 'bộ', 'bo',
    'hàng', 'hang', 'may', 'theo', 'yêu', 'yeu', 'cầu', 'cau', 'qa', 'jp', 'just',
    'play', 'sport', 'jsport', 'người', 'nguoi', 'lớn', 'lon', 'trẻ', 'tre', 'em',
})


def _fold(value: str) -> str:
    text = (value or '').casefold().strip()
    text = ''.join(
        ch for ch in unicodedata.normalize('NFD', text)
        if unicodedata.category(ch) != 'Mn'
    )
    return text


def _clean_kiot_name(value: str) -> str:
    text = (value or '').strip()
    text = re.sub(r'\s*\([^)]*trẻ\s*em[^)]*\)\s*', ' ', text, flags=re.I)
    text = re.sub(r'\s*\([^)]*người\s*lớn[^)]*\)\s*', ' ', text, flags=re.I)
    text = re.sub(r',?\s*các\s+màu.*$', '', text, flags=re.I)
    text = re.sub(r',?\s*các\s+size.*$', '', text, flags=re.I)
    text = re.sub(r'\s+', ' ', text).strip(' ,./-')
    return text


def _is_kids_label(value: str) -> bool:
    folded = _fold(value)
    return 'tre em' in folded or 'treem' in folded.replace(' ', '')


def _is_adult_label(value: str) -> bool:
    folded = _fold(value)
    return 'nguoi lon' in folded


def _needles_from_name(cleaned: str) -> list[str]:
    folded = _fold(cleaned)
    for key, aliases in _KEYWORD_ALIASES.items():
        if key in folded:
            return aliases

    # Ưu tiên cụm sau "CLB "
    m = re.search(r'\bclb\s+(.+)$', cleaned, flags=re.I)
    if m:
        club = m.group(1).strip()
        club_fold = _fold(club)
        for key, aliases in _KEYWORD_ALIASES.items():
            if key in club_fold or club_fold in key:
                return aliases
        # Nhiều CLB trong một dòng: AC Milan, Inter, Juve...
        parts = [p.strip(' .') for p in re.split(r'[,/]|…|\.{2,}', club) if p and p.strip(' .')]
        needles: list[str] = []
        for part in parts:
            pf = _fold(part)
            if pf in _KEYWORD_ALIASES:
                needles.extend(_KEYWORD_ALIASES[pf])
            elif len(part) >= 2 and pf not in _STOP_TOKENS:
                needles.append(part)
        if needles:
            return needles
        if len(club) >= 2:
            return [club]

    tokens = [t for t in re.split(r'[\s,/]+', cleaned) if t]
    picked: list[str] = []
    for token in reversed(tokens):
        ft = _fold(token)
        if ft in _STOP_TOKENS or len(ft) < 2:
            continue
        if ft in _KEYWORD_ALIASES:
            return _KEYWORD_ALIASES[ft]
        picked.append(token)
        if len(picked) >= 2:
            break
    if picked:
        return list(reversed(picked))
    return [cleaned] if cleaned else []


def _name_matches(product_name: str, needle: str) -> bool:
    name = product_name or ''
    n = (needle or '').strip()
    if not n:
        return False
    # Token ngắn: biên từ để tránh Optimus ⊃ mu
    if len(_fold(n).replace(' ', '')) <= 3:
        pattern = r'(?<!\w)' + re.escape(n.strip()) + r'(?!\w)'
        return re.search(pattern, name, flags=re.I) is not None
    return n.casefold() in name.casefold()


@dataclass
class AccountingImportResult:
    updated: int = 0
    skipped: int = 0
    unmatched_rows: int = 0
    styles_touched: int = 0
    errors: list[str] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)


def _read_invoice_rows(file_obj) -> list[dict]:
    wb = openpyxl.load_workbook(file_obj, read_only=True, data_only=True)
    try:
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        header_row = None
        header_idx = None
        for idx, row in enumerate(rows_iter, start=1):
            cells = [str(c).strip() if c is not None else '' for c in row]
            joined = ' '.join(cells).casefold()
            if 'mã sản phẩm' in joined or 'ma san pham' in _fold(joined):
                header_row = cells
                header_idx = idx
                break
        if not header_row:
            raise ValueError('Không tìm thấy dòng tiêu đề (cần cột «Mã sản phẩm»).')

        def col(*names: str) -> int | None:
            targets = {_fold(n) for n in names}
            for i, h in enumerate(header_row):
                if _fold(h) in targets:
                    return i
            return None

        i_code = col('Mã sản phẩm', 'Ma san pham')
        i_kiot = col('Tên Kiot', 'Ten Kiot', 'Tên kiot')
        i_hd = col('Tên hoá đơn/tem nhãn', 'Ten hoa don/tem nhan', 'Tên hoá đơn')
        if i_code is None:
            raise ValueError('Thiếu cột «Mã sản phẩm».')
        if i_kiot is None and i_hd is None:
            raise ValueError('Thiếu cột «Tên Kiot» hoặc «Tên hoá đơn/tem nhãn».')

        out: list[dict] = []
        for row in rows_iter:
            cells = list(row)
            code = str(cells[i_code]).strip() if i_code < len(cells) and cells[i_code] is not None else ''
            if not code or code.casefold() in {'none', 'nan'}:
                continue
            ten_kiot = ''
            if i_kiot is not None and i_kiot < len(cells) and cells[i_kiot] is not None:
                ten_kiot = str(cells[i_kiot]).strip()
            ten_hd = ''
            if i_hd is not None and i_hd < len(cells) and cells[i_hd] is not None:
                ten_hd = str(cells[i_hd]).strip()
            out.append({
                'accounting_code': code.upper() if code.isascii() else code.strip(),
                'ten_kiot': ten_kiot,
                'ten_hd': ten_hd,
                'line': header_idx + len(out) + 1,
            })
        return out
    finally:
        wb.close()


def _garment_kind(label: str) -> str | None:
    """ao | quan | None — lọc áo vs quần khi tên file nêu rõ."""
    folded = _fold(label)
    has_ao = bool(re.search(r'(^|[^a-z])ao([^a-z]|$)', folded))
    has_quan = 'quan' in folded
    if has_ao and not has_quan:
        return 'ao'
    if has_quan and not has_ao:
        return 'quan'
    return None


def _size_range_from_label(label: str) -> tuple[int, int] | None:
    folded = _fold(label)
    m = re.search(r'(?:sz|size)\s*(?:tu\s+)?(\d+)\s*[-–]\s*(\d+)', folded)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def _numeric_size(size_label: str) -> int | None:
    raw = (size_label or '').strip()
    if re.fullmatch(r'\d+', raw):
        return int(raw)
    return None


def _find_products_for_row(*, ten_kiot: str, ten_hd: str) -> list[Product]:
    label = ten_kiot or ten_hd
    cleaned = _clean_kiot_name(label)
    needles = _needles_from_name(cleaned)
    if not needles:
        return []

    kids = _is_kids_label(ten_kiot) or _is_kids_label(ten_hd)
    adult = _is_adult_label(ten_kiot) or _is_adult_label(ten_hd)
    if not kids and not adult:
        adult = True

    kind = _garment_kind(f'{ten_kiot} {ten_hd}')
    size_range = _size_range_from_label(f'{ten_kiot} {ten_hd}')

    q = Q()
    for needle in needles:
        token = needle.strip()
        if token:
            q |= Q(name__icontains=token)
    matched: list[Product] = []
    for product in Product.objects.filter(q).iterator(chunk_size=400):
        if not any(_name_matches(product.name, n) for n in needles):
            continue
        blob_fold = _fold(f'{product.name} {product.category_name}')
        is_kid_product = (
            'tre em' in blob_fold
            or 'treem' in blob_fold.replace(' ', '')
            or 'tre em' in _fold(product.category_name)
        )
        if kids and not is_kid_product:
            continue
        if adult and is_kid_product:
            continue
        name_fold = _fold(product.name)
        if kind == 'ao' and (name_fold.startswith('quan') or (
            'quan' in name_fold and not name_fold.startswith('ao') and 'ao ' not in name_fold
        )):
            continue
        if kind == 'quan' and not ('quan' in name_fold):
            continue
        if size_range:
            num = _numeric_size(product.size_label or '')
            if num is None or not (size_range[0] <= num <= size_range[1]):
                continue
        matched.append(product)
    return matched


@transaction.atomic
def import_accounting_from_invoice_excel(file_obj) -> AccountingImportResult:
    """Gán ``accounting_code`` (cột Mã sản phẩm) cho mọi SKU khớp Tên Kiot/HĐ."""
    result = AccountingImportResult()
    try:
        rows = _read_invoice_rows(file_obj)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(str(exc)[:300])
        return result

    def _row_rank(r: dict) -> tuple[int, int]:
        label = f"{r['ten_kiot']} {r['ten_hd']}"
        kids = 1 if (_is_kids_label(r['ten_kiot']) or _is_kids_label(r['ten_hd'])) else 0
        sized = 1 if _size_range_from_label(label) else 0
        return (kids, sized)

    rows.sort(key=_row_rank)

    styles: set[str] = set()
    changed_pks: set[int] = set()
    for row in rows:
        code = row['accounting_code']
        products = _find_products_for_row(ten_kiot=row['ten_kiot'], ten_hd=row['ten_hd'])
        if not products:
            result.unmatched_rows += 1
            if len(result.unmatched) < 40:
                hint = row['ten_kiot'] or row['ten_hd'] or '—'
                result.unmatched.append(f'{code}: không khớp «{hint[:80]}»')
            continue
        for product in products:
            if (product.accounting_code or '') != code:
                product.accounting_code = code
                product.save(update_fields=['accounting_code', 'updated_at'])
                changed_pks.add(product.pk)
            else:
                result.skipped += 1
            if product.style_code:
                styles.add(product.style_code)

    result.updated = len(changed_pks)
    result.styles_touched = len(styles)
    result.errors = list(result.unmatched[:20])
    return result
