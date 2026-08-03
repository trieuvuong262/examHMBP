"""Lấy mẫu kiểm tra theo AQL — ISO 2859-1 (một lần, kiểm tra thường).

Cấu trúc bảng 2-A của ISO 2859-1 rất đều: dọc mỗi cột AQL, số chấp nhận (Ac)
lần lượt là 0, 1, 2, 3, 5, 7, 10, 14, 21 khi cỡ mẫu tăng theo dãy chuẩn; kế
hoạch có Ac = 0 luôn nằm ở cỡ mẫu gần nhất với ``32 / AQL``. Nhờ vậy có thể
sinh lại đúng bảng mà không cần nhập tay hàng trăm ô, kèm luôn quy tắc mũi tên:

  * mũi tên xuống (cỡ mẫu quá nhỏ cho AQL đó) → dùng kế hoạch đầu tiên bên dưới
    (cỡ mẫu lớn hơn, Ac = 0);
  * mũi tên lên (vượt Ac = 21) → dùng kế hoạch cuối cùng bên trên (Ac = 21).

Nếu cỡ mẫu tính ra bằng hoặc lớn hơn cỡ lô thì kiểm tra 100% cỡ lô.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# Dãy cỡ mẫu chuẩn theo chữ mã (A → R)
LETTERS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'J', 'K', 'L', 'M', 'N', 'P', 'Q', 'R']
SAMPLE_SIZES = [2, 3, 5, 8, 13, 20, 32, 50, 80, 125, 200, 315, 500, 800, 1250, 2000]
AC_SEQUENCE = [0, 1, 2, 3, 5, 7, 10, 14, 21]

LEVELS = ['S-1', 'S-2', 'S-3', 'S-4', 'I', 'II', 'III']

# Bảng 1 — chữ mã cỡ mẫu: (cỡ lô tối đa, {mức kiểm tra: chữ mã})
_CODE_TABLE: list[tuple[int, dict[str, str]]] = [
    (8, {'S-1': 'A', 'S-2': 'A', 'S-3': 'A', 'S-4': 'A', 'I': 'A', 'II': 'A', 'III': 'B'}),
    (15, {'S-1': 'A', 'S-2': 'A', 'S-3': 'A', 'S-4': 'A', 'I': 'A', 'II': 'B', 'III': 'C'}),
    (25, {'S-1': 'A', 'S-2': 'A', 'S-3': 'B', 'S-4': 'B', 'I': 'B', 'II': 'C', 'III': 'D'}),
    (50, {'S-1': 'A', 'S-2': 'B', 'S-3': 'B', 'S-4': 'C', 'I': 'C', 'II': 'D', 'III': 'E'}),
    (90, {'S-1': 'B', 'S-2': 'B', 'S-3': 'C', 'S-4': 'C', 'I': 'C', 'II': 'E', 'III': 'F'}),
    (150, {'S-1': 'B', 'S-2': 'B', 'S-3': 'C', 'S-4': 'D', 'I': 'D', 'II': 'F', 'III': 'G'}),
    (280, {'S-1': 'B', 'S-2': 'C', 'S-3': 'D', 'S-4': 'E', 'I': 'E', 'II': 'G', 'III': 'H'}),
    (500, {'S-1': 'B', 'S-2': 'C', 'S-3': 'D', 'S-4': 'E', 'I': 'F', 'II': 'H', 'III': 'J'}),
    (1200, {'S-1': 'C', 'S-2': 'C', 'S-3': 'E', 'S-4': 'F', 'I': 'G', 'II': 'J', 'III': 'K'}),
    (3200, {'S-1': 'C', 'S-2': 'D', 'S-3': 'E', 'S-4': 'G', 'I': 'H', 'II': 'K', 'III': 'L'}),
    (10000, {'S-1': 'C', 'S-2': 'D', 'S-3': 'F', 'S-4': 'G', 'I': 'J', 'II': 'L', 'III': 'M'}),
    (35000, {'S-1': 'C', 'S-2': 'D', 'S-3': 'F', 'S-4': 'H', 'I': 'K', 'II': 'M', 'III': 'N'}),
    (150000, {'S-1': 'D', 'S-2': 'E', 'S-3': 'G', 'S-4': 'J', 'I': 'L', 'II': 'N', 'III': 'P'}),
    (500000, {'S-1': 'D', 'S-2': 'E', 'S-3': 'G', 'S-4': 'J', 'I': 'M', 'II': 'P', 'III': 'Q'}),
]
_CODE_TABLE_LAST = {'S-1': 'D', 'S-2': 'E', 'S-3': 'H', 'S-4': 'K', 'I': 'N', 'II': 'Q', 'III': 'R'}

# Các mức AQL tiêu chuẩn (%)
STANDARD_AQLS = [
    Decimal('0.010'), Decimal('0.015'), Decimal('0.025'), Decimal('0.040'), Decimal('0.065'),
    Decimal('0.10'), Decimal('0.15'), Decimal('0.25'), Decimal('0.40'), Decimal('0.65'),
    Decimal('1.0'), Decimal('1.5'), Decimal('2.5'), Decimal('4.0'), Decimal('6.5'),
    Decimal('10'), Decimal('15'),
]

_AC0_CONSTANT = Decimal('32')


class AqlError(Exception):
    pass


@dataclass(frozen=True)
class AqlPlan:
    """Kế hoạch lấy mẫu một lần."""

    lot_size: int
    aql: Decimal
    inspection_level: str
    code_letter: str
    sample_size: int
    accept: int
    reject: int
    full_inspection: bool = False
    arrow: str = ''  # '', 'down', 'up'

    @property
    def label(self) -> str:
        base = f'AQL {self.aql}% · mức {self.inspection_level} · chữ mã {self.code_letter}'
        if self.full_inspection:
            return f'{base} — kiểm 100% ({self.sample_size} cái)'
        return f'{base} — mẫu {self.sample_size}, chấp nhận ≤ {self.accept} lỗi'


def normalize_aql(value) -> Decimal:
    """Đưa AQL về mức tiêu chuẩn gần nhất (theo tỷ lệ, không theo hiệu số)."""
    try:
        raw = Decimal(str(value or 0))
    except Exception as exc:  # pragma: no cover
        raise AqlError('AQL không hợp lệ.') from exc
    if raw <= 0:
        return Decimal('2.5')
    best = STANDARD_AQLS[0]
    best_ratio = None
    for candidate in STANDARD_AQLS:
        ratio = raw / candidate if raw >= candidate else candidate / raw
        if best_ratio is None or ratio < best_ratio:
            best_ratio = ratio
            best = candidate
    return best


def normalize_level(value: str) -> str:
    level = (value or '').strip().upper()
    if level in LEVELS:
        return level
    if level in {'S1', 'S2', 'S3', 'S4'}:
        return f'S-{level[-1]}'
    return 'II'


def code_letter(lot_size: int, inspection_level: str = 'II') -> str:
    level = normalize_level(inspection_level)
    size = max(int(lot_size or 0), 0)
    if size < 2:
        return _CODE_TABLE[0][level]
    for upper, letters in _CODE_TABLE:
        if size <= upper:
            return letters[level]
    return _CODE_TABLE_LAST[level]


def _ac0_index(aql: Decimal) -> int:
    """Vị trí cỡ mẫu có Ac = 0 cho một cột AQL."""
    target = _AC0_CONSTANT / aql
    best_idx = 0
    best_ratio = None
    for idx, size in enumerate(SAMPLE_SIZES):
        value = Decimal(size)
        ratio = value / target if value >= target else target / value
        if best_ratio is None or ratio < best_ratio:
            best_ratio = ratio
            best_idx = idx
    return best_idx


def aql_sample_plan(
    *,
    lot_size,
    aql=Decimal('2.5'),
    inspection_level: str = 'II',
) -> AqlPlan:
    """Trả kế hoạch lấy mẫu ISO 2859-1 cho một lô."""
    size = int(Decimal(str(lot_size or 0)))
    if size <= 0:
        raise AqlError('Cỡ lô phải lớn hơn 0.')
    level = normalize_level(inspection_level)
    aql_value = normalize_aql(aql)
    letter = code_letter(size, level)
    letter_idx = LETTERS.index(letter)

    base_idx = _ac0_index(aql_value)
    offset = letter_idx - base_idx
    arrow = ''
    if offset < 0:
        arrow = 'down'
        offset = 0
    elif offset > len(AC_SEQUENCE) - 1:
        arrow = 'up'
        offset = len(AC_SEQUENCE) - 1

    resolved_idx = min(base_idx + offset, len(SAMPLE_SIZES) - 1)
    sample_size = SAMPLE_SIZES[resolved_idx]
    accept = AC_SEQUENCE[offset]

    full = False
    if sample_size >= size:
        sample_size = size
        full = True

    return AqlPlan(
        lot_size=size,
        aql=aql_value,
        inspection_level=level,
        code_letter=LETTERS[resolved_idx],
        sample_size=sample_size,
        accept=accept,
        reject=accept + 1,
        full_inspection=full,
        arrow=arrow,
    )
