"""Từ vựng SKU chuẩn: size, màu, giới tính.

Thiết kế và căn cứ số liệu: ``docs/integrations/central-product/sku-vocabulary.md``.
Module này là nguồn chân lý duy nhất cho việc chuẩn hóa; sau này export sang server
sản phẩm trung tâm thì lấy từ đây.

Nguyên tắc: ``Product.code`` là mã bất biến, KHÔNG sinh lại khi chuẩn hóa. Chỉ các
cột dữ liệu (``size_label``, ``color_code``, ``gender``) được chuẩn hóa.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------- giới tính

GENDER_NONE = ''
GENDER_MALE = 'NAM'
GENDER_FEMALE = 'NU'

GENDER_CHOICES = [
    (GENDER_NONE, '—'),
    (GENDER_MALE, 'Nam'),
    (GENDER_FEMALE, 'Nữ'),
]

# Hậu tố giới tính viết lồng trong size, vd. "XL-NỮ", "S-Nam"
_GENDER_SUFFIXES = {
    'nam': GENDER_MALE,
    'nữ': GENDER_FEMALE,
    'nu': GENDER_FEMALE,
}

# ---------------------------------------------------------------- thang đo size

SIZE_SCALE_ALPHA = 'ALPHA'
SIZE_SCALE_NUM = 'NUM'
SIZE_SCALE_OS = 'OS'
SIZE_SCALE_NONE = 'NONE'

SIZE_SCALE_CHOICES = [
    (SIZE_SCALE_ALPHA, 'Size chữ (XS–6XL)'),
    (SIZE_SCALE_NUM, 'Size số (trẻ em)'),
    (SIZE_SCALE_OS, 'Một size'),
    (SIZE_SCALE_NONE, 'Không có size'),
]

SIZE_OS = 'OS'
SIZE_NONE = 'NOSIZE'

# (thang đo, mã, tên hiển thị, thứ tự sắp xếp)
CANONICAL_SIZES: list[tuple[str, str, str, int]] = [
    (SIZE_SCALE_ALPHA, 'XS', 'XS', 10),
    (SIZE_SCALE_ALPHA, 'S', 'S', 20),
    (SIZE_SCALE_ALPHA, 'M', 'M', 30),
    (SIZE_SCALE_ALPHA, 'L', 'L', 40),
    (SIZE_SCALE_ALPHA, 'XL', 'XL', 50),
    (SIZE_SCALE_ALPHA, '2XL', '2XL', 60),
    (SIZE_SCALE_ALPHA, '3XL', '3XL', 70),
    (SIZE_SCALE_ALPHA, '4XL', '4XL', 80),
    (SIZE_SCALE_ALPHA, '5XL', '5XL', 90),
    (SIZE_SCALE_ALPHA, '6XL', '6XL', 100),
    (SIZE_SCALE_NUM, '1', 'Số 1', 210),
    (SIZE_SCALE_NUM, '3', 'Số 3', 220),
    (SIZE_SCALE_NUM, '5', 'Số 5', 230),
    (SIZE_SCALE_NUM, '7', 'Số 7', 240),
    (SIZE_SCALE_NUM, '9', 'Số 9', 250),
    (SIZE_SCALE_NUM, '11', 'Số 11', 260),
    (SIZE_SCALE_NUM, '13', 'Số 13', 270),
    (SIZE_SCALE_NUM, '15', 'Số 15', 280),
    (SIZE_SCALE_OS, SIZE_OS, 'Một size', 400),
    (SIZE_SCALE_NONE, SIZE_NONE, 'Không có size', 500),
]

SIZE_SCALE_BY_CODE = {code: scale for scale, code, _name, _order in CANONICAL_SIZES}

# Cách viết cũ → mã chuẩn
SIZE_ALIASES = {
    'XXL': '2XL',
    'XXXL': '3XL',
}

# Tên sản phẩm cho thấy mặt hàng không có khái niệm size. Chỉ áp dụng khi size hiện
# tại đang là OS hoặc rỗng — tránh đụng vào hàng có size thật.
NO_SIZE_NAME_HINTS = (
    'theo yêu cầu',
    'dịch vụ',
    'hàng sale',
    'phí giao hàng',
)

# Size thực chất là kích thước vật lý, vd. "39X54CM" — cần xử lý tay, không tự đổi.
DIMENSION_SIZE_RE = re.compile(r'^\d+\s*[X*]\s*\d+\s*(CM|MM|M)$', re.IGNORECASE)

# ---------------------------------------------------------------- màu

# Tên màu (như dữ liệu KiotViet ghi) → mã màu. 8 mã đầu đã có trong san_xuat_sxcolor,
# 14 mã sau được nghiệp vụ duyệt ngày 20/08/2026.
COLOR_CODES: dict[str, str] = {
    'Đen': 'BLK',
    'Trắng': 'WHT',
    'Xanh đen': 'NVY',
    'Đỏ': 'RED',
    'Xám': 'GRY',
    'Be': 'BEG',
    'Xanh dương': 'BLU',
    'Xanh lá': 'GRN',
    'Vàng': 'YEL',
    'Cam': 'ORG',
    'Xanh biển': 'SEA',
    'Xanh bích': 'TRQ',
    'Hồng': 'PNK',
    'Lông công': 'PCK',
    'Kem': 'CRM',
    'Đô': 'MRN',
    'Xanh da': 'SKY',
    'Cổ vịt': 'TEA',
    'Tím': 'PPL',
    'Xanh ngọc': 'JAD',
    'Xanh lý': 'LIM',
    'Xanh chuối': 'LGN',
}

COMBO_SEPARATOR = '-'

# Giá trị chốt cho dòng không xác định được màu — song song với SIZE_NONE. Dùng mã tường
# minh thay vì để rỗng, để phân biệt "đã kết luận không màu" với "chưa xử lý".
COLOR_NONE = 'NOCOLOR'
COLOR_NONE_LABEL = 'Không có màu'

# Cụm từ chứa tên màu nhưng không nói về màu. "Băng đô" là loại sản phẩm, không phải
# màu đô — nếu không loại ra thì 19 dòng băng đô bị gán màu MRN.
NON_COLOR_PHRASES = (
    'băng đô',
)

# Từ chỉ màu xuất hiện lẻ, không đủ thành tên màu chuẩn (vd. "Man city biển",
# "Trắng xanh"). Gặp từ này ngoài vùng đã khớp thì trả về cần-rà-soát thay vì đoán.
PARTIAL_COLOR_WORDS = (
    'xanh',
    'chuối',
    'vịt',
    'bích',
    'biển',
)

_COLOR_BY_FOLDED = {name.casefold(): name for name in COLOR_CODES}

# Sắp theo độ dài giảm dần để "Xanh đen" được xét trước "Đen"; regex alternation trả
# về khớp trái-nhất-dài-nhất và không chồng nhau.
_COLOR_PATTERN = re.compile(
    r'\b(?:' + '|'.join(re.escape(k) for k in sorted(_COLOR_BY_FOLDED, key=len, reverse=True)) + r')\b'
)

_FULL_NAME_SUFFIX_SEP = ' - '


def _squash(text: str) -> str:
    return re.sub(r'\s+', ' ', (text or '').strip())


# ---------------------------------------------------------------- size


@dataclass(frozen=True)
class SizeResult:
    size_code: str = ''
    scale: str = ''
    gender: str = GENDER_NONE
    needs_review: bool = False
    reason: str = ''

    @property
    def resolved(self) -> bool:
        return bool(self.size_code) and not self.needs_review


def normalize_size(raw_size: str, product_name: str = '') -> SizeResult:
    """Đưa một giá trị size thô về mã chuẩn + thang đo + giới tính tách riêng."""
    raw = _squash(raw_size).upper()
    name_folded = _squash(product_name).casefold()

    if DIMENSION_SIZE_RE.match(raw):
        return SizeResult(needs_review=True, reason=f'kích thước vật lý ({raw}) — xử lý tay')

    gender = GENDER_NONE
    if '-' in raw:
        head, _, tail = raw.rpartition('-')
        mapped = _GENDER_SUFFIXES.get(tail.casefold())
        if mapped and head:
            gender = mapped
            raw = head.strip()

    raw = SIZE_ALIASES.get(raw, raw)

    if not raw:
        return SizeResult(SIZE_NONE, SIZE_SCALE_NONE, gender)

    if raw == SIZE_OS:
        if any(hint in name_folded for hint in NO_SIZE_NAME_HINTS):
            return SizeResult(SIZE_NONE, SIZE_SCALE_NONE, gender)
        return SizeResult(SIZE_OS, SIZE_SCALE_OS, gender)

    scale = SIZE_SCALE_BY_CODE.get(raw)
    if scale:
        return SizeResult(raw, scale, gender)

    if raw.isdigit():
        return SizeResult(raw, SIZE_SCALE_NUM, gender, needs_review=True, reason=f'size số ngoài dải chuẩn: {raw}')

    return SizeResult(needs_review=True, reason=f'size không có trong từ vựng: {raw}')


# ---------------------------------------------------------------- màu


@dataclass(frozen=True)
class ColorResult:
    code: str = ''
    label: str = ''
    parts: tuple[str, ...] = field(default_factory=tuple)
    source: str = ''
    needs_review: bool = False
    reason: str = ''

    @property
    def resolved(self) -> bool:
        return bool(self.code) and not self.needs_review

    @property
    def is_combo(self) -> bool:
        return len(self.parts) > 1


def _blocked_spans(folded: str) -> list[tuple[int, int]]:
    spans = []
    for phrase in NON_COLOR_PHRASES:
        start = folded.find(phrase)
        while start != -1:
            spans.append((start, start + len(phrase)))
            start = folded.find(phrase, start + 1)
    return spans


def _scan_colors(text: str) -> tuple[list[str], list[tuple[int, int]]]:
    """Trả về (tên màu theo thứ tự xuất hiện, các vùng đã khớp)."""
    folded = _squash(text).casefold()
    if not folded:
        return [], []

    blocked = _blocked_spans(folded)
    names: list[str] = []
    spans: list[tuple[int, int]] = []

    for match in _COLOR_PATTERN.finditer(folded):
        start, end = match.span()
        if any(b_start <= start and end <= b_end for b_start, b_end in blocked):
            continue
        spans.append((start, end))
        name = _COLOR_BY_FOLDED[match.group(0)]
        if name not in names:
            names.append(name)
    return names, spans


def _leftover_partial_word(text: str, spans: list[tuple[int, int]]) -> str:
    """Từ chỉ màu còn sót bên ngoài các vùng đã khớp."""
    folded = _squash(text).casefold()
    for word in PARTIAL_COLOR_WORDS:
        for match in re.finditer(rf'\b{re.escape(word)}\b', folded):
            start, end = match.span()
            if not any(s <= start and end <= e for s, e in spans):
                return word
    return ''


def build_color_code(parts: list[str] | tuple[str, ...]) -> str:
    """Mã tổ hợp = ghép mã theo thứ tự xuất hiện, vd. Xanh đen + Trắng → NVY-WHT."""
    return COMBO_SEPARATOR.join(COLOR_CODES[name] for name in parts)


def build_color_label(parts: list[str] | tuple[str, ...]) -> str:
    return ' '.join(parts) if len(parts) > 1 else (parts[0] if parts else '')


def resolve_color(name: str, full_name: str = '', color_label: str = '') -> ColorResult:
    """Suy ra màu của sản phẩm.

    Thứ tự tin cậy: ``color_label`` (KiotViet đã ghi, chỉ sai hoa/thường và thiếu mã)
    → hậu tố sau dấu ``-`` cuối của ``full_name`` (khuôn ``"<tên> - <Màu>"``)
    → dò trong ``name``.
    """
    candidates: list[tuple[str, str]] = []
    if _squash(color_label):
        candidates.append(('color_label', color_label))
    squashed_full = _squash(full_name)
    if _FULL_NAME_SUFFIX_SEP in squashed_full:
        candidates.append(('full_name', squashed_full.rsplit(_FULL_NAME_SUFFIX_SEP, 1)[1]))
    candidates.append(('name', name or ''))

    pending: ColorResult | None = None
    pending_leftover = ''
    pending_parts: set[str] = set()

    for source, text in candidates:
        parts, spans = _scan_colors(text)
        leftover = _leftover_partial_word(text, spans)
        if leftover:
            if pending is None:
                pending = ColorResult(
                    source=source,
                    needs_review=True,
                    reason=f'từ chỉ màu chưa rõ "{leftover}" trong "{_squash(text)}"',
                )
                pending_leftover = leftover
                pending_parts = set(parts)
            continue
        if not parts:
            continue
        # Nguồn tin cậy hơn còn từ lửng: chỉ nhận nguồn sau nếu nó làm rõ chính từ đó và
        # giữ nguyên các màu đã chắc (vd. label "đen xanh" + tên "… đen xanh da" →
        # BLK-SKY), tránh nhận một bộ màu khác hẳn.
        if pending_leftover:
            explains = any(pending_leftover in part.casefold() for part in parts)
            if not explains or not pending_parts.issubset(parts):
                continue
        return ColorResult(
            code=build_color_code(parts),
            label=build_color_label(parts),
            parts=tuple(parts),
            source=source,
        )

    return pending or ColorResult(needs_review=True, reason='không tìm thấy tên màu')
