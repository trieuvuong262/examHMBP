"""Chức danh / vị trí nhân sự — JustPlay (sản xuất quần áo thể thao)."""

DEFAULT_POSITION = 'Công nhân may'

DEFAULT_DEPARTMENTS = [
    'CÔNG TY TNHH JUST PLAY',
    'ĐẢM BẢO CHẤT LƯỢNG',
    'HÀNH CHÍNH NHÂN SỰ',
    'KẾ HOẠCH SẢN XUẤT',
    'KINH DOANH - MARKETING',
    'R&D',
    'SẢN XUẤT',
    'TÀI CHÍNH KẾ TOÁN',
]

DEFAULT_DIVISIONS = [
    'QC',
    'Ép logo',
    'Giao Hàng',
    'HCNS',
    'Marketing',
    'Merchandise',
    'Thiết kế sản phẩm',
    'IE',
    'May mẫu',
    'Kế toán',
    'Kho nguyên phụ liệu',
    'Điều phối (Kiểm đếm xuất nhập hàng)',
]

GENDER_CHOICES = [
    ('M', 'Nam'),
    ('F', 'Nữ'),
]

GENDER_FORM_CHOICES = [('', '-- Chọn giới tính --'), *GENDER_CHOICES]

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
    """Chuẩn hóa vị trí công việc từ DB/Excel cũ."""
    if not value:
        return DEFAULT_POSITION
    value = str(value).strip()
    if value in VALID_POSITIONS:
        return value
    return LEGACY_POSITION_MAP.get(value, DEFAULT_POSITION)


def normalize_gender(value):
    if not value:
        return ''
    raw = str(value).strip().lower()
    mapping = {
        'nam': 'M', 'm': 'M', 'male': 'M',
        'nữ': 'F', 'nu': 'F', 'female': 'F', 'f': 'F',
    }
    if raw.upper() in {'M', 'F'}:
        return raw.upper()
    return mapping.get(raw, '')


def parse_excel_date(value):
    """Chuyển giá trị Excel thành date hoặc None."""
    if value is None or value == '':
        return None
    if hasattr(value, 'date') and callable(getattr(value, 'date', None)):
        try:
            return value.date()
        except Exception:
            pass
    if hasattr(value, 'year'):
        return value
    from datetime import datetime
    text = str(value).strip()
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


# Cột Excel nhân sự (thứ tự cố định — dùng chung import/export/template)
EXCEL_HR_HEADERS = [
    'Mã NS', 'Họ và tên', 'Account', 'Phòng ban', 'Bộ phận',
    'Vị trí', 'Chức vụ', 'Ngày vào', 'Ngày sinh', 'Giới tính',
]
EXCEL_IMPORT_OPTIONAL_HEADERS = ['password', 'email']
EXCEL_ALL_HEADERS = EXCEL_HR_HEADERS + EXCEL_IMPORT_OPTIONAL_HEADERS

# Map tên cột Excel (lower, strip) → field profile
EXCEL_COLUMN_MAP = {
    'ma_ns': 'employee_code',
    'ma ns': 'employee_code',
    'mã ns': 'employee_code',
    'employee_code': 'employee_code',
    'ho_va_ten': 'full_name',
    'ho va ten': 'full_name',
    'họ và tên': 'full_name',
    'full_name': 'full_name',
    'account': 'username',
    'username': 'username',
    'phong_ban': 'department',
    'phong ban': 'department',
    'phòng ban': 'department',
    'department': 'department',
    'bo_phan': 'division',
    'bo phan': 'division',
    'bộ phận': 'division',
    'division': 'division',
    'vi_tri': 'job_position',
    'vi tri': 'job_position',
    'vị trí': 'job_position',
    'job_position': 'job_position',
    'chuc_vu': 'job_title',
    'chuc vu': 'job_title',
    'chức vụ': 'job_title',
    'job_title': 'job_title',
    'chuc_danh': 'job_position',  # cột cũ
    'position': 'job_position',
    'ngay_vao': 'join_date',
    'ngay vao': 'join_date',
    'ngày vào': 'join_date',
    'join_date': 'join_date',
    'ngay_sinh': 'date_of_birth',
    'ngay sinh': 'date_of_birth',
    'ngày sinh': 'date_of_birth',
    'date_of_birth': 'date_of_birth',
    'gioi_tinh': 'gender',
    'gioi tinh': 'gender',
    'giới tính': 'gender',
    'gender': 'gender',
    'email': 'email',
    'password': 'password',
}


def format_excel_date(value):
    return value.strftime('%d/%m/%Y') if value else ''


def gender_excel_label(code):
    if not code:
        return ''
    labels = {'M': 'Nam', 'F': 'Nữ'}
    return labels.get(code, '')


def resolve_department(name):
    """Tìm phòng ban theo tên (không phân biệt hoa thường)."""
    if not name or not str(name).strip():
        return None
    from hrm.models import Department
    text = str(name).strip()
    dept = Department.objects.filter(name__iexact=text, is_active=True).first()
    if not dept:
        dept = Department.objects.filter(name__iexact=text).first()
    return dept


def resolve_division(name, department=None):
    """Tìm bộ phận theo tên; ưu tiên đúng phòng ban khi import."""
    if not name or not str(name).strip():
        return None
    from hrm.models import Division
    text = str(name).strip()
    if department is not None:
        div = Division.objects.filter(
            name__iexact=text,
            department=department,
            is_active=True,
        ).first()
        if not div:
            div = Division.objects.filter(name__iexact=text, department=department).first()
        if div:
            return div
    div = Division.objects.filter(name__iexact=text, is_active=True).first()
    if not div:
        div = Division.objects.filter(name__iexact=text).first()
    return div


def user_to_excel_row(user):
    """Chuyển User + Profile thành dict theo EXCEL_ALL_HEADERS."""
    profile = getattr(user, 'profile', None)
    dept_name = ''
    div_name = ''
    if profile and profile.department_id:
        dept_name = profile.department.name
    if profile and profile.division_id:
        div_name = profile.division.name
    return {
        'Mã NS': profile.employee_code if profile and profile.employee_code else '',
        'Họ và tên': profile.full_name if profile and profile.full_name else (user.first_name or ''),
        'Account': user.username,
        'Phòng ban': dept_name,
        'Bộ phận': div_name,
        'Vị trí': profile.job_position if profile else '',
        'Chức vụ': profile.job_title if profile else '',
        'Ngày vào': format_excel_date(profile.join_date if profile else None),
        'Ngày sinh': format_excel_date(profile.date_of_birth if profile else None),
        'Giới tính': gender_excel_label(profile.gender if profile else ''),
        'password': '',
        'email': user.email or '',
    }


def profile_defaults_from_import(data):
    """Dict field profile từ dữ liệu đã parse Excel."""
    dept = resolve_department(data.get('department', ''))
    return {
        'employee_code': data.get('employee_code') or None,
        'full_name': data.get('full_name', ''),
        'department': dept,
        'division': resolve_division(data.get('division', ''), department=dept),
        'job_position': (data.get('job_position') or '').strip(),
        'job_title': data.get('job_title', ''),
        'join_date': data.get('join_date'),
        'date_of_birth': data.get('date_of_birth'),
        'gender': data.get('gender', ''),
    }


def row_to_profile_data(row):
    """Đọc một dòng Excel (Series/dict) thành dict chuẩn."""
    data = {}
    for key, val in row.items():
        col = str(key).strip().lower()
        field = EXCEL_COLUMN_MAP.get(col)
        if not field:
            continue
        if field in {'join_date', 'date_of_birth'}:
            data[field] = parse_excel_date(val)
        elif field == 'gender':
            data[field] = normalize_gender(val)
        elif field == 'job_position':
            data[field] = str(val).strip() if val is not None and str(val).strip() else ''
        else:
            data[field] = str(val).strip() if val is not None and str(val).strip() else ''
    return data
