import re
import secrets
import string
import unicodedata

from django.contrib.auth.models import User

EMAIL_DOMAIN = 'justplay.vn'
PROBATION_JOB_LABEL = 'Nhân viên thử việc'
PROBATION_PERMISSION_GROUP_NAME = 'Nhân viên thử việc'
EMPLOYEE_CODE_BASE = 440


def remove_vietnamese_accents(text):
    text = str(text).replace('đ', 'd').replace('Đ', 'D')
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')
    return text.lower().strip()


def _name_parts(full_name: str) -> tuple[str, str]:
    """
    Tách họ tên: tên gọi (từ cuối) + chữ cái đầu các phần còn lại.
    Nguyễn Thành Nam -> ('nam', 'nt')
    Trần Thái Viết Hưng -> ('hung', 'ttv')
    """
    clean_name = remove_vietnamese_accents(full_name)
    parts = [p for p in clean_name.split() if p]
    if not parts:
        return '', ''
    if len(parts) == 1:
        return parts[0], ''
    given_name = parts[-1]
    initials = ''.join(part[0] for part in parts[:-1] if part)
    return given_name, initials


def build_hm_username_base(full_name: str) -> str:
    """Gợi ý account gốc — chưa xử lý trùng."""
    given_name, initials = _name_parts(full_name)
    if not given_name:
        return 'user'
    if initials:
        return f'{given_name}.{initials}'
    return given_name


def _username_exists(username: str, *, exclude_user_id=None) -> bool:
    qs = User.objects.filter(username__iexact=username)
    if exclude_user_id:
        qs = qs.exclude(pk=exclude_user_id)
    return qs.exists()


def generate_hm_username(full_name, *, exclude_user_id=None) -> str:
    """
    Account dạng tên.ho_ten_dem — ví dụ nam.nt, hung.ttv.
    Trùng thì thêm số: nam.nt1, nam.nt2...
    """
    base = build_hm_username_base(full_name)
    if not _username_exists(base, exclude_user_id=exclude_user_id):
        return base

    counter = 1
    while True:
        candidate = f'{base}{counter}'
        if not _username_exists(candidate, exclude_user_id=exclude_user_id):
            return candidate
        counter += 1


def generate_hm_email(username: str) -> str:
    return f'{(username or "").strip().lower()}@{EMAIL_DOMAIN}'


def next_employee_code() -> str:
    """Mã NS = số lớn nhất trong hệ thống + 1 (nền từ 440)."""
    from hrm.models import Profile

    max_num = EMPLOYEE_CODE_BASE
    codes = (
        Profile.objects.exclude(employee_code__isnull=True)
        .exclude(employee_code='')
        .values_list('employee_code', flat=True)
    )
    for code in codes:
        for match in re.findall(r'\d+', str(code)):
            try:
                max_num = max(max_num, int(match))
            except ValueError:
                continue
    return str(max_num + 1)


def get_probation_permission_group():
    from hrm.models import PermissionGroup

    group = PermissionGroup.objects.filter(
        name__iexact=PROBATION_PERMISSION_GROUP_NAME,
    ).first()
    if group:
        return group
    return (
        PermissionGroup.objects.filter(name__icontains='thử việc')
        .order_by('name')
        .first()
    )


def suggest_hm_credentials(full_name, *, exclude_user_id=None, include_employee_code=True) -> dict:
    username = generate_hm_username(full_name, exclude_user_id=exclude_user_id)
    payload = {
        'username': username,
        'email': generate_hm_email(username),
    }
    if include_employee_code:
        payload['employee_code'] = next_employee_code()
    return payload


def generate_secure_password(length=8):
    """Tạo mật khẩu ngẫu nhiên bảo mật cao"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))
