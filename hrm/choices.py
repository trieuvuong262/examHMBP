"""Chức danh nhân sự — JustPlay (sản xuất quần áo thể thao)."""

DEFAULT_POSITION = 'Công nhân may'

POSITION_CHOICES = [
    ('Công nhân may', 'Công nhân may'),
    ('Công nhân cắt', 'Công nhân cắt'),
    ('Thợ in/thêu', 'Thợ in/thêu'),
    ('Nhân viên QC', 'Nhân viên QC'),
    ('Đóng gói', 'Đóng gói'),
    ('KHSX', 'KHSX'),
    ('Kho vận', 'Kho vận'),
    ('Kỹ thuật rập', 'Kỹ thuật rập'),
    ('Thiết kế mẫu', 'Thiết kế mẫu'),
    ('Tổ trưởng', 'Tổ trưởng'),
    ('HR / HCNS', 'HR / HCNS'),
    ('Kế toán', 'Kế toán'),
    ('Kinh doanh', 'Kinh doanh'),
    ('IT', 'IT'),
]

POSITION_FORM_CHOICES = [('', '-- Vui lòng chọn chức danh --'), *POSITION_CHOICES]

# Map chức danh y tế cũ → may mặc (migration / import Excel cũ)
LEGACY_POSITION_MAP = {
    'Bác Sĩ': 'Thiết kế mẫu',
    'Điều Dưỡng': 'Nhân viên QC',
    'Dược Sĩ': 'Kho vận',
    'Kỹ Thuật viên': 'Công nhân may',
    'Khối Hỗ trợ': 'HR / HCNS',
}

VALID_POSITIONS = {code for code, _ in POSITION_CHOICES}


def normalize_position(value):
    """Chuẩn hóa chức danh từ DB/Excel cũ."""
    if not value:
        return DEFAULT_POSITION
    value = str(value).strip()
    if value in VALID_POSITIONS:
        return value
    return LEGACY_POSITION_MAP.get(value, DEFAULT_POSITION)
