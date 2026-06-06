from django.contrib.auth import get_user_model
from django.test import Client

from kiotviet.formatters import format_description_html, format_product_group_detail
from kiotviet.models import KvProduct
from kiotviet.product_groups import get_product_group
from kiotviet.sync_service import current_retailer

retailer = current_retailer()
sample = KvProduct.objects.filter(
    retailer=retailer,
    description__icontains='<p>',
).first()
if not sample:
    sample = KvProduct.objects.filter(
        retailer=retailer,
        description__icontains='<br>',
    ).first()

if not sample:
    print('NO_HTML_DESCRIPTION_PRODUCT')
else:
    print('product_id', sample.kiotviet_id, 'code', sample.code)
    print('raw_prefix', (sample.description or '')[:120])
    group = get_product_group(retailer, sample.kiotviet_id)
    formatted = format_product_group_detail(group)
    html = formatted.get('description_html', '')
    print('html_has_br', '<br' in html)
    print('html_has_escaped_p', '&lt;p&gt;' in html)
    print('html_prefix', html[:160])

user = User.objects.filter(is_active=True, is_superuser=True).first() or User.objects.filter(is_active=True).first()
if user and sample:
    client = Client(HTTP_HOST='portal.justplay.vn')
    client.force_login(user)
    resp = client.get(f'/kiotviet/hang-hoa/{sample.kiotviet_id}/')
    body = resp.content.decode('utf-8', errors='replace')
    print('detail_http', resp.status_code)
    print('page_has_kv_product_description', 'kv-product-description' in body)
    print('page_shows_literal_lt_p', '&lt;p&gt;Balo' in body or '&lt;p&gt;' in body[:5000])
