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
    'IN ÉP',
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
    """Chuyển giá trị Excel thành date hoặc None.

    Cột ngày từ pandas thường là datetime64 — ô trống thành NaT và
    ``DataFrame.fillna('')`` không thay được NaT. Gọi ``.date()`` trên NaT
    vẫn trả NaT; lưu vào DateField sẽ lỗi ``NaTType does not support utcoffset``.
    """
    from datetime import date, datetime

    if value is None or value == '':
        return None
    try:
        import pandas as pd
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    if hasattr(value, 'to_pydatetime') and callable(getattr(value, 'to_pydatetime', None)):
        try:
            return value.to_pydatetime().date()
        except Exception:
            pass

    if hasattr(value, 'date') and callable(getattr(value, 'date', None)):
        try:
            result = value.date()
            try:
                import pandas as pd
                if pd.isna(result):
                    return None
            except (TypeError, ValueError):
                pass
            if isinstance(result, datetime):
                return result.date()
            if isinstance(result, date):
                return result
        except Exception:
            pass

    text = str(value).strip()
    if not text or text.lower() in {'nat', 'nan', 'none', 'null'}:
        return None
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


# Cột Excel nhân sự (thứ tự cố định — dùng chung import/export/template)
EXCEL_HR_HEADERS = [
    'Mã NS', 'Họ và tên', 'SĐT', 'Account', 'Phòng ban', 'Bộ phận',
    'Vị trí', 'Chức vụ', 'Ngày vào', 'Ngày sinh', 'Giới tính',
    'Vai trò HT', 'Nhóm quyền', 'Trạng thái',
]
EXCEL_IMPORT_OPTIONAL_HEADERS = ['password', 'email']
EXCEL_ALL_HEADERS = EXCEL_HR_HEADERS + EXCEL_IMPORT_OPTIONAL_HEADERS

DEFAULT_PORTAL_PASSWORD = 'justplay@123'


def user_export_password_hint(user, profile=None):
    """Mật khẩu khi xuất Excel: trống nếu đã đăng nhập và đã đổi mật khẩu."""
    profile = profile if profile is not None else getattr(user, 'profile', None)
    if user.last_login and profile and not profile.must_change_password:
        return ''
    return DEFAULT_PORTAL_PASSWORD

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
    'sdt': 'phone',
    'sđt': 'phone',
    'so_dien_thoai': 'phone',
    'so dien thoai': 'phone',
    'số điện thoại': 'phone',
    'dien_thoai': 'phone',
    'dien thoai': 'phone',
    'điện thoại': 'phone',
    'phone': 'phone',
    'mobile': 'phone',
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
    'vai_tro_ht': 'role',
    'vai tro ht': 'role',
    'vai trò ht': 'role',
    'role': 'role',
    'nhom_quyen': 'permission_group',
    'nhom quyen': 'permission_group',
    'nhóm quyền': 'permission_group',
    'permission_group': 'permission_group',
    'trang_thai': 'is_employed',
    'trang thai': 'is_employed',
    'trạng thái': 'is_employed',
    'is_employed': 'is_employed',
    'thu_viec': 'on_probation',
    'thu viec': 'on_probation',
    'thử việc': 'on_probation',
    'on_probation': 'on_probation',
}


def parse_probation_status(value, default=True):
    if value is None or value == '':
        return default
    if isinstance(value, bool):
        return value
    raw = str(value).strip().lower()
    yes = {'1', 'true', 'yes', 'y', 'có', 'co', 'thử việc', 'thu viec', 'thuviec', 'on'}
    no = {'0', 'false', 'no', 'n', 'không', 'khong', 'off'}
    if raw in yes:
        return True
    if raw in no:
        return False
    return default


def format_excel_date(value):
    return value.strftime('%d/%m/%Y') if value else ''


def gender_excel_label(code):
    if not code:
        return ''
    labels = {'M': 'Nam', 'F': 'Nữ'}
    return labels.get(code, '')


def employment_excel_label(is_employed):
    if is_employed is None:
        return ''
    return 'Đang làm' if is_employed else 'Nghỉ việc'


def role_excel_label(code):
    if not code:
        return ''
    from hrm.permissions import ROLE_CHOICES
    return dict(ROLE_CHOICES).get(code, code)


def resolve_role(value):
    """Mã vai trò (EMPLOYEE) hoặc nhãn tiếng Việt (Nhân viên)."""
    if value is None or str(value).strip() == '':
        return None
    from hrm.permissions import ROLE_CHOICES
    raw = str(value).strip()
    upper = raw.upper().replace(' ', '_').replace('-', '_')
    valid_codes = {code for code, _ in ROLE_CHOICES}
    if upper in valid_codes:
        return upper
    labels = {label.lower(): code for code, label in ROLE_CHOICES}
    return labels.get(raw.lower())


def resolve_permission_group(name_or_slug):
    """Tìm nhóm quyền theo tên hoặc slug."""
    if not name_or_slug or not str(name_or_slug).strip():
        return None
    from hrm.models import PermissionGroup
    text = str(name_or_slug).strip()
    group = PermissionGroup.objects.filter(name__iexact=text).first()
    if group:
        return group
    return PermissionGroup.objects.filter(slug__iexact=text).first()


def parse_employment_status(value, default=True):
    if value is None or value == '':
        return default
    if isinstance(value, bool):
        return value
    raw = str(value).strip().lower()
    active = {
        '1', 'true', 'yes', 'y', 'đang làm', 'dang lam', 'danglam', 'active', 'lam', 'đang lam',
    }
    inactive = {
        '0', 'false', 'no', 'n', 'nghỉ việc', 'nghi viec', 'nghiviec', 'inactive', 'nghỉ', 'nghi',
    }
    if raw in active:
        return True
    if raw in inactive:
        return False
    return default


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
    from hrm.phone import format_phone_vn

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
        'SĐT': format_phone_vn(profile.phone) if profile else '',
        'Account': user.username,
        'Phòng ban': dept_name,
        'Bộ phận': div_name,
        'Vị trí': profile.job_position if profile else '',
        'Chức vụ': profile.job_title if profile else '',
        'Ngày vào': format_excel_date(profile.join_date if profile else None),
        'Thử việc': 'Có' if profile and profile.on_probation else 'Không',
        'Ngày sinh': format_excel_date(profile.date_of_birth if profile else None),
        'Giới tính': gender_excel_label(profile.gender if profile else ''),
        'Vai trò HT': role_excel_label(profile.role if profile else ''),
        'Nhóm quyền': (
            profile.permission_group.name
            if profile and profile.permission_group_id
            else ''
        ),
        'Trạng thái': employment_excel_label(profile.is_employed if profile else True),
        'password': user_export_password_hint(user, profile),
        'email': user.email or '',
    }


def profile_defaults_from_import(data):
    """Dict field profile từ dữ liệu đã parse Excel."""
    from hrm.group_permissions import default_group_for_role
    from hrm.permissions import ROLE_EMPLOYEE
    from hrm.phone import is_valid_vn_mobile, normalize_phone
    from hrm.probation import resolve_on_probation

    dept = resolve_department(data.get('department', ''))
    role = resolve_role(data.get('role', '')) or ROLE_EMPLOYEE
    permission_group = resolve_permission_group(data.get('permission_group', ''))
    if not permission_group:
        permission_group = default_group_for_role(role)
    join_date = data.get('join_date')
    on_probation_raw = data.get('on_probation')
    requested = parse_probation_status(on_probation_raw, default=True)
    on_probation = resolve_on_probation(join_date, requested)
    phone = normalize_phone(data.get('phone', ''))
    if phone and not is_valid_vn_mobile(phone):
        phone = ''
    return {
        'employee_code': data.get('employee_code') or None,
        'full_name': data.get('full_name', ''),
        'phone': phone,
        'department': dept,
        'division': resolve_division(data.get('division', ''), department=dept),
        'job_position': (data.get('job_position') or '').strip(),
        'job_title': data.get('job_title', ''),
        'join_date': join_date,
        'on_probation': on_probation,
        'date_of_birth': data.get('date_of_birth'),
        'gender': data.get('gender', ''),
        'role': role,
        'permission_group': permission_group,
        'is_employed': parse_employment_status(data.get('is_employed'), default=True),
    }


def row_to_profile_data(row):
    """Đọc một dòng Excel (Series/dict) thành dict chuẩn."""
    from hrm.phone import normalize_phone

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
        elif field == 'phone':
            data[field] = normalize_phone(val)
        elif field == 'job_position':
            data[field] = str(val).strip() if val is not None and str(val).strip() else ''
        elif field == 'is_employed':
            data[field] = val
        elif field == 'on_probation':
            data[field] = val
        else:
            data[field] = str(val).strip() if val is not None and str(val).strip() else ''
    return data
