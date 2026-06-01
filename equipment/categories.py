"""Loại thiết bị xưởng may — nhóm theo công đoạn (không gồm hạ tầng M&E và phòng ban hỗ trợ)."""

# (mã, tên hiển thị, nhóm import)
_CUTTING = [
    ('CUT_SPREAD', 'Máy trải vải', 'cutting'),
    ('CUT_TABLE', 'Bàn cắt / spreading table', 'cutting'),
    ('CUT_MACHINE', 'Máy cắt (dao rung, đĩa, laser…)', 'cutting'),
    ('CUT_AUX', 'Máy cắt phụ (band knife, notch, drill…)', 'cutting'),
    ('CUT_MEASURE', 'Cân / đo vải', 'cutting'),
    ('CUT_CAD', 'Plotter / CAD cắt', 'cutting'),
]

_SEWING = [
    ('SEW_LOCKSTITCH', 'Máy may 1 kim (lockstitch)', 'sewing'),
    ('SEW_DOUBLE', 'Máy may 2 kim', 'sewing'),
    ('SEW_OVERLOCK', 'Máy may overlock', 'sewing'),
    ('SEW_INTERLOCK', 'Máy may interlock / flatlock', 'sewing'),
    ('SEW_SPECIAL', 'Máy may chuyên dụng (nút, túi, bartack…)', 'sewing'),
    ('SEW_AUTO', 'Máy may tự động / CNC', 'sewing'),
    ('SEW_AUX', 'Phụ trợ may (bàn, ghế, đèn, hút bụi…)', 'sewing'),
]

_FINISHING = [
    ('FINISH_IRON', 'Bàn ủi / máy ủi hơi', 'finishing'),
    ('FINISH_PRESS', 'Máy ép / heat press', 'finishing'),
    ('FINISH_TUNNEL', 'Tunnel / form finisher', 'finishing'),
    ('FINISH_TRIM', 'Cắt chỉ / xử lý lông', 'finishing'),
]

_PRINT_EMB = [
    ('EMB_MACHINE', 'Máy thêu', 'print_emb'),
    ('PRINT_MACHINE', 'Máy in (screen, DTG, sublimation…)', 'print_emb'),
    ('LABEL_PRESS', 'Máy ép nhãn / logo', 'print_emb'),
    ('BARCODE_PRINT', 'Máy in tem / mã vạch', 'print_emb'),
]

_WASH = [
    ('WASH_MACHINE', 'Máy giặt công nghiệp', 'wash'),
    ('DRY_MACHINE', 'Máy sấy', 'wash'),
    ('WASH_EFFECT', 'Máy xử lý wash effect', 'wash'),
]

_QC = [
    ('QC_LAB', 'Thiết bị phòng lab / đo lường', 'qc'),
    ('QC_MEASURE', 'Bàn đo / template QC', 'qc'),
    ('QC_DETECT', 'Kim detector / metal detector', 'qc'),
    ('QC_CAMERA', 'Camera kiểm QC', 'qc'),
]

_WAREHOUSE = [
    ('PACK_MACHINE', 'Máy đóng gói (hút chân không, co film…)', 'warehouse'),
    ('PACK_SCALE', 'Cân đóng gói', 'warehouse'),
    ('WARE_CONVEYOR', 'Băng chuyền / băng tải', 'warehouse'),
    ('WARE_FORKLIFT', 'Xe nâng / pallet jack', 'warehouse'),
    ('WARE_RACK', 'Kệ / pallet', 'warehouse'),
    ('WARE_SCANNER', 'Máy quét barcode / RFID', 'warehouse'),
]

_SAMPLE = [
    ('SAMPLE_SEW', 'Máy may mẫu', 'sample'),
    ('SAMPLE_EMB', 'Máy thêu / in mẫu', 'sample'),
    ('SAMPLE_MEASURE', 'Thiết bị đo mẫu', 'sample'),
    ('SAMPLE_CUT', 'Plotter / cắt mẫu', 'sample'),
]

_IT = [
    ('PC', 'Máy tính bàn (PC)', 'it'),
    ('Laptop', 'Laptop', 'it'),
    ('Printer', 'Máy in', 'it'),
    ('Network', 'Server / Thiết bị mạng', 'it'),
    ('Internet', 'Internet / Đường truyền', 'it'),
    ('CCTV', 'Camera an ninh (CCTV)', 'it'),
    ('PHONE', 'Tổng đài / walkie-talkie', 'it'),
    ('ATTENDANCE', 'Máy chấm công', 'it'),
    ('DISPLAY', 'Màn hình / TV / Andon', 'it'),
]

_OTHER = [
    ('Tool', 'Dụng cụ / bàn ghế xưởng', 'general'),
    ('PROD_OTHER', 'Máy sản xuất khác', 'general'),
    ('Other', 'Khác', 'general'),
]

# Giữ tương thích dữ liệu cũ
_LEGACY = [
    ('Production', 'Máy sản xuất (cũ)', 'general'),
]

CATEGORY_CHOICES = (
    _CUTTING + _SEWING + _FINISHING + _PRINT_EMB + _WASH + _QC
    + _WAREHOUSE + _SAMPLE + _IT + _OTHER + _LEGACY
)

# Django model choices: (mã, nhãn)
DEVICE_CATEGORY_CHOICES = [(code, label) for code, label, _group in CATEGORY_CHOICES]

CATEGORY_GROUP_LABELS = {
    'cutting': '1. Cắt',
    'sewing': '2. May',
    'finishing': '3. Ủi – hoàn thiện',
    'print_emb': '4. In – thêu – trang trí',
    'wash': '5. Giặt – xử lý vải',
    'qc': '6. Kiểm tra chất lượng (QC)',
    'warehouse': '7. Đóng gói – kho – logistics',
    'sample': '8. Phòng mẫu',
    'it': '10. IT / Văn phòng / An ninh',
    'general': 'Khác',
}

CATEGORY_GROUPS = []
_seen_groups = set()
for code, label, group in CATEGORY_CHOICES:
    if group not in _seen_groups:
        _seen_groups.add(group)
        CATEGORY_GROUPS.append((group, CATEGORY_GROUP_LABELS.get(group, group)))
    # rebuild grouped choices for templates
CATEGORY_CHOICES_BY_GROUP = []
for group_code, group_label in CATEGORY_GROUPS:
    items = [(c, lbl) for c, lbl, g in CATEGORY_CHOICES if g == group_code]
    CATEGORY_CHOICES_BY_GROUP.append((group_code, group_label, items))

CATEGORY_MAP = dict(DEVICE_CATEGORY_CHOICES)
VALID_CATEGORY_CODES = set(CATEGORY_MAP)

# Alias tên cũ / tiếng Việt trong file Excel
CATEGORY_ALIASES = {
    'pc': 'PC',
    'may tinh': 'PC',
    'máy tính': 'PC',
    'máy tính bàn': 'PC',
    'laptop': 'Laptop',
    'may in': 'Printer',
    'máy in': 'Printer',
    'printer': 'Printer',
    'network': 'Network',
    'server': 'Network',
    'internet': 'Internet',
    'cctv': 'CCTV',
    'camera': 'CCTV',
    'production': 'Production',
    'máy sản xuất': 'PROD_OTHER',
    'may san xuat': 'PROD_OTHER',
    'tool': 'Tool',
    'other': 'Other',
    'khác': 'Other',
}

# Cột import/export
IMPORT_COLUMNS_BASE = [
    ('name', 'Tên thiết bị', True),
    ('managed_by', 'Bộ phận QL (IT / MAINTENANCE / OTHER)', False),
    ('status', 'Trạng thái (new / active / broken / maintenance / scrapped)', False),
    ('usage_department_text', 'Phòng ban sử dụng', False),
    ('usage_room', 'Phòng / vị trí (Line, khu vực…)', False),
    ('assigned_user_text', 'Người dùng / người phụ trách', False),
    ('contact_email', 'Email liên hệ', False),
    ('handover_date', 'Ngày bàn giao (YYYY-MM-DD)', False),
    ('model_number', 'Model / hãng', False),
    ('serial_number', 'Serial Number', False),
    ('description', 'Mô tả', False),
    ('quantity', 'Số lượng', False),
    ('unit_price', 'Đơn giá (VNĐ)', False),
]

IMPORT_COLUMNS_IT = IMPORT_COLUMNS_BASE + [
    ('configuration', 'Cấu hình (RAM, CPU…)', False),
    ('hostname', 'Hostname', False),
    ('ip_address', 'Địa chỉ IP', False),
]

IMPORT_COLUMNS_MACHINE = IMPORT_COLUMNS_BASE  # máy xưởng — không bắt buộc IP/hostname

IMPORT_PROFILE_BY_GROUP = {
    'it': 'it',
    'cutting': 'machine',
    'sewing': 'machine',
    'finishing': 'machine',
    'print_emb': 'machine',
    'wash': 'machine',
    'qc': 'machine',
    'warehouse': 'machine',
    'sample': 'machine',
    'general': 'machine',
}

IMPORT_PROFILE_COLUMNS = {
    'it': IMPORT_COLUMNS_IT,
    'machine': IMPORT_COLUMNS_MACHINE,
}

# Mẫu dữ liệu theo loại
SAMPLE_ROWS = {
    'PC': {
        'name': 'PC Dell OptiPlex 3080 — Line 2',
        'managed_by': 'IT',
        'status': 'active',
        'usage_department_text': 'Phòng Sản xuất',
        'usage_room': 'Line 2',
        'assigned_user_text': 'Nguyễn Văn A',
        'contact_email': 'user@justplay.vn',
        'handover_date': '2025-01-15',
        'model_number': 'Dell OptiPlex 3080 SFF',
        'serial_number': 'CN-0X1234',
        'configuration': 'Core i5, RAM 16GB, SSD 512GB',
        'description': 'Máy cấp mới đợt 1',
        'hostname': 'PC-SX-02',
        'ip_address': '192.168.1.15',
        'quantity': 1,
        'unit_price': 15000000,
    },
    'SEW_LOCKSTITCH': {
        'name': 'Máy may 1 kim Juki DDL-8700 — Line 3',
        'managed_by': 'MAINTENANCE',
        'status': 'active',
        'usage_department_text': 'Xưởng may',
        'usage_room': 'Line 3 — vị trí 12',
        'assigned_user_text': 'Trần Thị B',
        'contact_email': '',
        'handover_date': '2024-06-01',
        'model_number': 'Juki DDL-8700',
        'serial_number': 'JK-8700-00123',
        'description': 'Máy may áo thân',
        'quantity': 1,
        'unit_price': 25000000,
    },
    'CUT_MACHINE': {
        'name': 'Máy cắt dao rung Bullmer',
        'managed_by': 'MAINTENANCE',
        'status': 'active',
        'usage_department_text': 'Phòng cắt',
        'usage_room': 'Khu cắt A',
        'assigned_user_text': 'Lê Văn C',
        'handover_date': '2023-11-20',
        'model_number': 'Bullmer PRO系列',
        'serial_number': 'BM-2023-456',
        'description': 'Máy cắt tự động 1 lớp',
        'quantity': 1,
        'unit_price': 850000000,
    },
    'PACK_MACHINE': {
        'name': 'Máy hút chân không đóng gói',
        'managed_by': 'MAINTENANCE',
        'status': 'active',
        'usage_department_text': 'Kho thành phẩm',
        'usage_room': 'Khu đóng gói',
        'model_number': 'DZ-400/2S',
        'serial_number': 'DZ400-789',
        'quantity': 2,
        'unit_price': 45000000,
    },
    'EMB_MACHINE': {
        'name': 'Máy thêu Tajima 6 đầu',
        'managed_by': 'MAINTENANCE',
        'status': 'active',
        'usage_department_text': 'Xưởng thêu',
        'usage_room': 'Khu thêu 1',
        'model_number': 'Tajima TMAR-KC',
        'serial_number': 'TJ-6H-001',
        'quantity': 1,
        'unit_price': 320000000,
    },
}


def category_group_for_code(code: str) -> str:
    for c, _label, group in CATEGORY_CHOICES:
        if c == code:
            return group
    return 'general'


def import_profile_for_category(code: str) -> str:
    group = category_group_for_code(code)
    return IMPORT_PROFILE_BY_GROUP.get(group, 'machine')


def import_columns_for_category(code: str) -> list:
    from equipment.services.device_categories import import_profile_for_code
    profile = import_profile_for_code(code)
    return IMPORT_PROFILE_COLUMNS.get(profile, IMPORT_COLUMNS_MACHINE)


def normalize_category(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text in VALID_CATEGORY_CODES:
        return text
    lower = text.lower()
    if lower in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[lower]
    for code, label in CATEGORY_CHOICES:
        if lower == label.lower():
            return code
    return None


def sample_row_for_category(code: str) -> dict:
    if code in SAMPLE_ROWS:
        return dict(SAMPLE_ROWS[code])
    profile = import_profile_for_category(code)
    label = CATEGORY_MAP.get(code, code)
    row = {
        'name': f'Ví dụ: {label}',
        'managed_by': 'MAINTENANCE' if profile == 'machine' else 'IT',
        'status': 'active',
        'usage_department_text': 'Phòng ban mẫu',
        'usage_room': 'Vị trí mẫu',
        'quantity': 1,
        'unit_price': 0,
    }
    if profile == 'it':
        row.update({
            'hostname': 'PC-MAU-01',
            'ip_address': '192.168.1.100',
            'configuration': 'Cấu hình mẫu',
        })
    return row
