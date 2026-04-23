import unicodedata
import secrets
import string
from django.contrib.auth.models import User

def remove_vietnamese_accents(text):
    text = str(text).replace('đ', 'd').replace('Đ', 'D')
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')
    return text.lower().strip()

def generate_hm_username(full_name):
    """ Tạo username dạng ten.ho1@hoanmy.com """
    clean_name = remove_vietnamese_accents(full_name)
    parts = clean_name.split()
    
    if not parts:
        base = "user.hm"
    elif len(parts) == 1:
        base = parts[0]
    else:
        ho = parts[0]
        ten = parts[-1]
        base = f"{ten}.{ho}"
    
    counter = 1
    username = f"{base}{counter}@hoanmy.com"
    while User.objects.filter(username=username).exists():
        counter += 1
        username = f"{base}{counter}@hoanmy.com"
        
    return username

def generate_secure_password(length=8):
    """Tạo mật khẩu ngẫu nhiên bảo mật cao"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))