"""Kiểm tra trang Hàng hoá sau đổi bộ lọc."""
from django.contrib.auth import get_user_model
from django.test import Client

from kiotviet.product_groups import browse_product_groups
from kiotviet.sync_service import current_retailer

User = get_user_model()
user = User.objects.filter(is_active=True, is_superuser=True).first() or User.objects.filter(is_active=True).first()
if not user:
    print('NO_USER')
    raise SystemExit(1)

client = Client(HTTP_HOST='portal.justplay.vn')
client.force_login(user)
resp = client.get('/kiotviet/hang-hoa/')
body = resp.content.decode('utf-8', errors='replace')
print('HTTP', resp.status_code)
print('has_kv_search_type', 'kv-search-type' in body)
print('has_category_q', 'category_q' in body)
print('has_tra_theo_label', 'Tra theo' in body)
print('has_ten_nhom_label', 'Tên nhóm' in body)
print('has_unified_search', 'Mã hoặc tên hàng' in body)
print('has_filter_more', 'Bộ lọc thêm' in body)

retailer = current_retailer()
groups, total = browse_product_groups(page=1, per_page=5, retailer=retailer, search='SP')
print('search_SP_total', total)
if groups:
    print('first_group', groups[0].name[:40], groups[0].codes[:2])
