import unicodedata
import secrets
import string
from django.contrib.auth.models import User

def remove_vietnamese_accents(text):
    text = str(text).replace('đ', 'd').replace('Đ', 'D')
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')
    return text.lower().strip()

def generate_hm_username(full_name):
    """ Tạo username dạng ten.ho@hoanmy.com (Nếu trùng mới thêm số) """
    
    # 1. Xử lý an toàn nếu truyền vào tên rỗng hoặc None
    if not full_name or str(full_name).strip() == "" or str(full_name).lower() == "none":
        base = "user.hm"
    else:
        # 2. Xóa dấu và tách từ
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
    
    # 3. Ép kiểu username lần đầu (KHÔNG CÓ SỐ)
    username = f"{base}@hoanmy.com"
    counter = 1
    
    # 4. Kiểm tra trong Database, nếu ĐÃ TỒN TẠI thì mới gắn thêm số vào
    while User.objects.filter(username=username).exists():
        username = f"{base}{counter}@hoanmy.com"
        counter += 1
        
    return username

def generate_secure_password(length=8):
    """Tạo mật khẩu ngẫu nhiên bảo mật cao"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))