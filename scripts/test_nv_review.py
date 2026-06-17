#!/usr/bin/env python3
import re
import requests

BASE = 'https://portal.justplay.vn'
s = requests.Session()
s.headers['User-Agent'] = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)'
r = s.get(f'{BASE}/accounts/login/', timeout=30)
csrf = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.text).group(1)
s.post(f'{BASE}/accounts/login/', data={'csrfmiddlewaretoken': csrf, 'username': 'nv.tb', 'password': '123123sS@', 'next': '/reports/today/'}, headers={'Referer': f'{BASE}/accounts/login/'}, allow_redirects=True, timeout=30)
review = s.get(f'{BASE}/reports/today/?phase=review', timeout=30)
print('review status', review.status_code)
print('has review-grid-root', 'review-grid-root' in review.text)
print('has hourly-grid-data', 'hourly-grid-data' in review.text)
print('empty msg', 'Chưa có mã hàng đã kết thúc' in review.text)
print('new empty msg', 'Chưa có sản lượng' in review.text)
print('grand_total in page', 'grand_total' in review.text or 'Tổng:' in review.text)
# parse json_script content length
m = re.search(r'id="hourly-grid-data"[^>]*>([^<]+)<', review.text)
if m:
    import json
    data = json.loads(m.group(1))
    print('rows', len(data.get('rows', [])))
    print('grand_total', data.get('grand_total'))
    print('has_unfinalized', data.get('has_unfinalized'))
else:
    print('no grid json')
