import unicodedata
import secrets
import string
from django.contrib.auth.models import User


def remove_vietnamese_accents(text):
    text = str(text).replace('đ', 'd').replace('Đ', 'D')
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')
    return text.lower().strip()


def generate_hm_username(full_name):
    """
    Tạo username dạng Tên + chữ cái đầu họ + chữ cái đầu tên đệm.
    Ví dụ: Nguyễn Thành An -> Annt
    """
    if not full_name or str(full_name).strip() == "" or str(full_name).lower() == "none":
        base = "User"
    else:
        clean_name = remove_vietnamese_accents(full_name)
        parts = clean_name.split()

        if not parts:
            base = "User"
        elif len(parts) == 1:
            base = parts[0].capitalize()
        elif len(parts) == 2:
            ho, ten = parts[0], parts[-1]
            base = f"{ten.capitalize()}{ho[0]}"
        else:
            ho = parts[0]
            ten = parts[-1]
            dem = parts[1]
            base = f"{ten.capitalize()}{ho[0]}{dem[0]}"

    username = base
    counter = 2
    while User.objects.filter(username__iexact=username).exists():
        username = f"{base}{counter}"
        counter += 1

    return username


def generate_secure_password(length=8):
    """Tạo mật khẩu ngẫu nhiên bảo mật cao"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))
