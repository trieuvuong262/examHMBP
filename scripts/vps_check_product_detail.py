from kiotviet.formatters import format_product_group_detail
from kiotviet.product_groups import get_product_group
from kiotviet.sync_service import current_retailer

retailer = current_retailer()
product_id = 32020642
raw = get_product_group(retailer, product_id)
if not raw:
    print('NOT_FOUND')
    raise SystemExit(0)

p = format_product_group_detail(raw)
print('name:', p['name'][:80])
print('is_group:', p['is_group'], 'variants:', p['variant_count'])
print('images:', len(p['images']))
print('total_on_hand:', p['total_on_hand'])
print('min_price:', p['min_price'], 'max_price:', p['max_price'])
print('category:', p['category_path'][:60] if p['category_path'] != '—' else '—')
print('desc_len:', len(p.get('description_html') or ''))
print('stock_rows:', len(p['stock_matrix']['rows']))
print('stock_cols:', len(p['stock_matrix']['columns']))
